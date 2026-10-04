from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .models import Profile, ScheduleWindow, SendJob
from .normalize import normalize_text


def utc_now() -> datetime:
    return datetime.now(UTC)


class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool = ConnectionPool(
            conninfo=database_url,
            min_size=1,
            max_size=4,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        self.pool.wait(timeout=10)
        self._poller_connection: psycopg.Connection | None = None

    def close(self) -> None:
        if self._poller_connection is not None:
            try:
                self._poller_connection.execute(
                    "SELECT pg_advisory_unlock(hashtext('foody:telegram-poller'))"
                )
            finally:
                self._poller_connection.close()
                self._poller_connection = None
        self.pool.close()

    def check(self) -> bool:
        try:
            with self.pool.connection(timeout=3) as conn:
                return bool(conn.execute("SELECT 1").fetchone())
        except (psycopg.Error, TimeoutError):
            return False

    def acquire_poller_lock(self) -> bool:
        if self._poller_connection is not None:
            return True
        conn = psycopg.connect(self.database_url, autocommit=True)
        acquired = conn.execute("SELECT pg_try_advisory_lock(hashtext('foody:telegram-poller'))").fetchone()[
            0
        ]
        if not acquired:
            conn.close()
            return False
        self._poller_connection = conn
        return True

    def poller_lock_alive(self) -> bool:
        if self._poller_connection is None:
            return False
        try:
            return self._poller_connection.execute("SELECT 1").fetchone()[0] == 1
        except psycopg.Error:
            return False

    def recover_inflight(self) -> int:
        """Never blindly retry jobs that may have reached Telegram before a restart."""
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE outbound_jobs
                SET status='ambiguous', completed_at=now(), updated_at=now(), error_class='ProcessRestart'
                WHERE status='sending'
                RETURNING id
                """
            ).fetchall()
        return len(row)

    def cleanup(self) -> None:
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM event_logs WHERE created_at < now() - interval '14 days'")
            conn.execute("DELETE FROM telegram_updates WHERE processed_at < now() - interval '7 days'")
            conn.execute(
                """
                UPDATE outbound_jobs SET status='cancelled',completed_at=now(),updated_at=now(),
                    error_class='ProfileDeleted'
                WHERE status='pending' AND profile_id IS NULL
                """
            )
            conn.execute(
                """
                DELETE FROM outbound_jobs
                WHERE completed_at < now() - interval '30 days'
                  AND status IN ('sent','cancelled','failed')
                """
            )
            conn.execute(
                """
                DELETE FROM outbound_jobs
                WHERE completed_at < now() - interval '90 days' AND status='ambiguous'
                """
            )

    def log(
        self,
        event_type: str,
        profile_id=None,
        chat_id=None,
        message_id=None,
        sender_id=None,
        detail=None,
    ) -> None:
        try:
            safe_detail = str(detail or "")[:500]
            with self.pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO event_logs(
                        event_type, profile_id, source_chat_id, source_message_id, sender_id, detail
                    ) VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (event_type, profile_id, chat_id, message_id, sender_id, safe_detail),
                )
        except psycopg.Error:
            pass

    def record_ignored(self, chat_id: int, message_id: int) -> bool:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO telegram_updates(chat_id,message_id,status) VALUES (%s,%s,'ignored')
                ON CONFLICT DO NOTHING RETURNING message_id
                """,
                (chat_id, message_id),
            ).fetchone()
        return row is not None

    def enqueue_match(self, profile: Profile, chat_id: int, message_id: int, sender_id: int) -> str:
        """Atomically deduplicate an update and persist its outbound work."""
        with self.pool.connection() as conn, conn.transaction():
            inserted = conn.execute(
                """
                    INSERT INTO telegram_updates(chat_id,message_id,status) VALUES (%s,%s,'queued')
                    ON CONFLICT DO NOTHING RETURNING message_id
                    """,
                (chat_id, message_id),
            ).fetchone()
            if inserted is None:
                return "duplicate"
            replies = conn.execute(
                "SELECT text FROM reply_messages WHERE profile_id=%s ORDER BY id",
                (profile.id,),
            ).fetchall()
            if not replies:
                conn.execute(
                    "UPDATE telegram_updates SET status='ignored' WHERE chat_id=%s AND message_id=%s",
                    (chat_id, message_id),
                )
                return "no_reply"
            reply = random.choice(replies)["text"]
            delay = random.uniform(profile.delay_min_seconds, profile.delay_max_seconds)
            conn.execute(
                """
                    INSERT INTO outbound_jobs(
                        profile_id,source_chat_id,source_message_id,sender_id,reply_text,available_at
                    ) VALUES (%s,%s,%s,%s,%s,now()+(%s * interval '1 second'))
                    """,
                (profile.id, chat_id, message_id, sender_id, reply, delay),
            )
            conn.execute(
                """
                    INSERT INTO event_logs(
                        event_type,profile_id,source_chat_id,source_message_id,sender_id,detail
                    ) VALUES ('MATCH',%s,%s,%s,%s,%s)
                    """,
                (profile.id, chat_id, message_id, sender_id, profile.name[:500]),
            )
        return "queued"

    def claim_next_job(self) -> SendJob | None:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                    SELECT id,profile_id,source_chat_id,source_message_id,sender_id,reply_text,
                           attempt_count,available_at
                    FROM outbound_jobs
                    WHERE status='pending' AND available_at <= now() AND profile_id IS NOT NULL
                    ORDER BY available_at,id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                    UPDATE outbound_jobs
                    SET status='sending',claimed_at=now(),updated_at=now(),attempt_count=attempt_count+1
                    WHERE id=%s
                    """,
                (row["id"],),
            )
        return SendJob(
            id=row["id"],
            profile_id=row["profile_id"],
            source_chat_id=row["source_chat_id"],
            source_message_id=row["source_message_id"],
            sender_id=row["sender_id"],
            reply_text=row["reply_text"],
            attempt_count=row["attempt_count"] + 1,
            available_at=row["available_at"],
        )

    def defer_job(self, job_id: int, seconds: int, error_class: str) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                UPDATE outbound_jobs
                SET status='pending', available_at=now()+(%s * interval '1 second'),
                    claimed_at=NULL, updated_at=now(), error_class=%s
                WHERE id=%s AND status='sending'
                """,
                (seconds, error_class[:100], job_id),
            )

    def global_send_wait(self, minimum_interval: float) -> float:
        if minimum_interval <= 0:
            return 0.0
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT GREATEST(
                    0,
                    EXTRACT(EPOCH FROM (
                        last_successful_send_at + (%s * interval '1 second') - now()
                    ))
                ) AS wait_seconds
                FROM service_runtime
                WHERE singleton=TRUE
                """,
                (minimum_interval,),
            ).fetchone()
        return float(row["wait_seconds"] or 0) if row else 0.0

    def finish_job(self, job: SendJob, status: str, error_class: str | None = None) -> None:
        if status not in {"sent", "cancelled", "failed", "ambiguous"}:
            raise ValueError("Invalid terminal job status")
        with self.pool.connection() as conn, conn.transaction():
            transitioned = conn.execute(
                """
                UPDATE outbound_jobs
                SET status=%s,completed_at=now(),updated_at=now(),error_class=%s
                WHERE id=%s AND status='sending'
                RETURNING id
                """,
                (status, error_class[:100] if error_class else None, job.id),
            ).fetchone()
            if transitioned is None:
                return
            event_type = {
                "sent": "SENT",
                "cancelled": "SEND_CANCELLED",
                "failed": "SEND_ERROR",
                "ambiguous": "SEND_AMBIGUOUS",
            }[status]
            if status == "sent":
                conn.execute("UPDATE service_runtime SET last_successful_send_at=now() WHERE singleton=TRUE")
                conn.execute(
                    """
                    INSERT INTO contact_history(profile_id,sender_id,last_sent_at) VALUES (%s,%s,now())
                    ON CONFLICT(profile_id,sender_id) DO UPDATE SET last_sent_at=excluded.last_sent_at
                    """,
                    (job.profile_id, job.sender_id),
                )
            conn.execute(
                """
                INSERT INTO event_logs(
                    event_type,profile_id,source_chat_id,source_message_id,sender_id,detail
                ) VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    event_type,
                    job.profile_id,
                    job.source_chat_id,
                    job.source_message_id,
                    job.sender_id,
                    error_class[:100] if error_class else "",
                ),
            )

    def profiles(self) -> list[Profile]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT * FROM profiles ORDER BY id").fetchall()
            result = []
            for row in rows:
                groups = conn.execute(
                    "SELECT id FROM rule_groups WHERE profile_id=%s ORDER BY position,id", (row["id"],)
                ).fetchall()
                rule_groups = [
                    [
                        term["normalized_term"]
                        for term in conn.execute(
                            "SELECT normalized_term FROM rule_terms WHERE group_id=%s ORDER BY id",
                            (group["id"],),
                        ).fetchall()
                    ]
                    for group in groups
                ]
                not_terms = [
                    item["normalized_term"]
                    for item in conn.execute(
                        "SELECT normalized_term FROM not_terms WHERE profile_id=%s ORDER BY id",
                        (row["id"],),
                    ).fetchall()
                ]
                replies = [
                    item["text"]
                    for item in conn.execute(
                        "SELECT text FROM reply_messages WHERE profile_id=%s ORDER BY id", (row["id"],)
                    ).fetchall()
                ]
                windows = [
                    ScheduleWindow(item["weekday"], item["start_minute"], item["end_minute"])
                    for item in conn.execute(
                        """
                        SELECT weekday,start_minute,end_minute FROM schedule_windows
                        WHERE profile_id=%s ORDER BY weekday,start_minute
                        """,
                        (row["id"],),
                    ).fetchall()
                ]
                result.append(
                    Profile(
                        row["id"],
                        row["name"],
                        row["mode"],
                        row["cooldown_seconds"],
                        row["delay_min_seconds"],
                        row["delay_max_seconds"],
                        rule_groups,
                        not_terms,
                        replies,
                        windows,
                    )
                )
        return result

    def profile(self, profile_id: int) -> Profile | None:
        return next((profile for profile in self.profiles() if profile.id == profile_id), None)

    def create_profile(self, name: str, cooldown: int) -> int:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO profiles(name,mode,cooldown_seconds) VALUES (%s,'OFF',%s) RETURNING id
                """,
                (name.strip(), cooldown),
            ).fetchone()
        return int(row["id"])

    def update_profile(self, profile_id: int, *, name=None, mode=None, cooldown=None) -> None:
        field, value = (
            ("name", name)
            if name is not None
            else (("mode", mode) if mode is not None else ("cooldown_seconds", cooldown))
        )
        with self.pool.connection() as conn:
            conn.execute(f"UPDATE profiles SET {field}=%s,updated_at=now() WHERE id=%s", (value, profile_id))

    def update_delay(self, profile_id: int, minimum: int, maximum: int) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                UPDATE profiles SET delay_min_seconds=%s,delay_max_seconds=%s,updated_at=now() WHERE id=%s
                """,
                (minimum, maximum, profile_id),
            )

    def delete_profile(self, profile_id: int) -> None:
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM profiles WHERE id=%s", (profile_id,))

    def all_off(self) -> None:
        with self.pool.connection() as conn:
            conn.execute("UPDATE profiles SET mode='OFF',updated_at=now()")

    def add_group(self, profile_id: int, terms: list[str]) -> None:
        with self.pool.connection() as conn, conn.transaction():
            position = conn.execute(
                "SELECT COALESCE(MAX(position),-1)+1 AS position FROM rule_groups WHERE profile_id=%s",
                (profile_id,),
            ).fetchone()["position"]
            group_id = conn.execute(
                "INSERT INTO rule_groups(profile_id,position) VALUES (%s,%s) RETURNING id",
                (profile_id, position),
            ).fetchone()["id"]
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO rule_terms(group_id,term,normalized_term) VALUES (%s,%s,%s)",
                    [(group_id, term, normalize_text(term)) for term in terms],
                )

    def delete_group(self, group_id: int) -> None:
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM rule_groups WHERE id=%s", (group_id,))

    def add_term(self, group_id: int, term: str) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO rule_terms(group_id,term,normalized_term) VALUES (%s,%s,%s)",
                (group_id, term, normalize_text(term)),
            )

    def delete_term(self, term_id: int) -> None:
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM rule_terms WHERE id=%s", (term_id,))

    def term_rows(self, group_id: int):
        with self.pool.connection() as conn:
            return conn.execute(
                "SELECT id,term FROM rule_terms WHERE group_id=%s ORDER BY id", (group_id,)
            ).fetchall()

    def group_rows(self, profile_id: int):
        with self.pool.connection() as conn:
            groups = conn.execute(
                "SELECT id FROM rule_groups WHERE profile_id=%s ORDER BY position,id", (profile_id,)
            ).fetchall()
            return [
                (
                    group["id"],
                    [
                        term["term"]
                        for term in conn.execute(
                            "SELECT term FROM rule_terms WHERE group_id=%s ORDER BY id", (group["id"],)
                        ).fetchall()
                    ],
                )
                for group in groups
            ]

    def add_not_terms(self, profile_id: int, terms: list[str]) -> None:
        with self.pool.connection() as conn, conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO not_terms(profile_id,term,normalized_term) VALUES (%s,%s,%s)",
                [(profile_id, term, normalize_text(term)) for term in terms],
            )

    def list_items(self, table: str, profile_id: int):
        allowed = {"not_terms": "term", "reply_messages": "text"}
        column = allowed[table]
        with self.pool.connection() as conn:
            return conn.execute(
                f"SELECT id,{column} AS value FROM {table} WHERE profile_id=%s ORDER BY id", (profile_id,)
            ).fetchall()

    def add_reply(self, profile_id: int, text: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("INSERT INTO reply_messages(profile_id,text) VALUES (%s,%s)", (profile_id, text))

    def delete_item(self, table: str, item_id: int) -> None:
        if table not in {"not_terms", "reply_messages", "schedule_windows"}:
            raise ValueError("Invalid table")
        with self.pool.connection() as conn:
            conn.execute(f"DELETE FROM {table} WHERE id=%s", (item_id,))

    def add_window(self, profile_id: int, weekday: int, start: int, end: int) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO schedule_windows(profile_id,weekday,start_minute,end_minute) VALUES (%s,%s,%s,%s)
                """,
                (profile_id, weekday, start, end),
            )

    def windows(self, profile_id: int, weekday: int):
        with self.pool.connection() as conn:
            return conn.execute(
                """
                SELECT id,start_minute,end_minute FROM schedule_windows
                WHERE profile_id=%s AND weekday=%s ORDER BY start_minute
                """,
                (profile_id, weekday),
            ).fetchall()

    def in_cooldown(self, profile_id: int, sender_id: int, seconds: int) -> bool:
        if seconds <= 0:
            return False
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT last_sent_at FROM contact_history WHERE profile_id=%s AND sender_id=%s",
                (profile_id, sender_id),
            ).fetchone()
        return bool(row and row["last_sent_at"] > utc_now() - timedelta(seconds=seconds))

    def opt_out(self, sender_id: int) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO recipient_opt_outs(sender_id) VALUES (%s) ON CONFLICT DO NOTHING", (sender_id,)
            )

    def opt_in(self, sender_id: int) -> None:
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM recipient_opt_outs WHERE sender_id=%s", (sender_id,))

    def is_opted_out(self, sender_id: int) -> bool:
        with self.pool.connection() as conn:
            return (
                conn.execute("SELECT 1 FROM recipient_opt_outs WHERE sender_id=%s", (sender_id,)).fetchone()
                is not None
            )

    def recent_logs(self, limit=15):
        with self.pool.connection() as conn:
            return conn.execute(
                "SELECT created_at,event_type,detail FROM event_logs ORDER BY id DESC LIMIT %s", (limit,)
            ).fetchall()

    def last_event(self, event_type: str):
        with self.pool.connection() as conn:
            return conn.execute(
                "SELECT created_at,detail FROM event_logs WHERE event_type=%s ORDER BY id DESC LIMIT 1",
                (event_type,),
            ).fetchone()

    def queue_counts(self) -> dict[str, int]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT status,count(*) AS count FROM outbound_jobs GROUP BY status"
            ).fetchall()
        return {row["status"]: row["count"] for row in rows}
