from __future__ import annotations

import asyncio
import logging
from collections import deque
from contextlib import suppress
from datetime import UTC, datetime
from time import monotonic

from telethon.errors import FloodWaitError
from telethon.tl.types import User

from .rules import profile_matches
from .scheduler import is_profile_active

log = logging.getLogger(__name__)


class HistoryPoller:
    """One awaited history request per cycle; never schedule overlapping polls."""

    def __init__(self, client, db, notify, target_chat_id, app_timezone, stop, interval=1.0):
        self.client = client
        self.db = db
        self.notify = notify
        self.target_chat_id = target_chat_id
        self.timezone = app_timezone
        self.stop = stop
        self.interval = interval
        self.seen: set[int] = set()
        self.seen_order: deque[int] = deque()
        self.active_ids: tuple[int, ...] | None = None
        self.active_since: dict[int, datetime] = {}
        self.cycle = 0

    async def wait(self, seconds):
        with suppress(TimeoutError):
            await asyncio.wait_for(self.stop.wait(), timeout=seconds)

    async def active_profiles(self):
        profiles = await asyncio.to_thread(self.db.profiles)
        now = datetime.now(self.timezone)
        active = sorted((p for p in profiles if is_profile_active(p, now)), key=lambda p: p.id)
        ids = tuple(p.id for p in active)
        self.active_since = {pid: self.active_since.get(pid, now.astimezone(UTC)) for pid in ids}
        if ids != self.active_ids:
            self.active_ids = ids
            log.info(
                "History polling activity changed",
                extra={"event": "poll_activity", "active_profiles": len(ids)},
            )
        return active

    def remember(self, message_id):
        if message_id in self.seen:
            return
        self.seen.add(message_id)
        self.seen_order.append(message_id)
        if len(self.seen_order) > 1000:
            self.seen.discard(self.seen_order.popleft())

    async def poll_once(self):
        started = monotonic()
        profiles = await self.active_profiles()
        profiles_ms = (monotonic() - started) * 1000
        if not profiles or self.stop.is_set():
            return
        self.cycle += 1
        trace = f"poll-{self.cycle}"
        log.info("Fetching latest three messages", extra={"event": "poll_started", "trace_id": trace})
        fetch_start = monotonic()
        messages = await self.client.get_messages(self.target_chat_id, limit=3)
        fetch_ms = (monotonic() - fetch_start) * 1000
        log.info(
            "History request completed",
            extra={
                "event": "poll_fetched",
                "trace_id": trace,
                "fetch_ms": round(fetch_ms, 1),
                "message_count": len(messages),
            },
        )
        if self.stop.is_set():
            return
        # Settings may have changed while Telegram was answering.
        recheck_start = monotonic()
        profiles = await self.active_profiles()
        profiles_ms += (monotonic() - recheck_start) * 1000
        processing_start = monotonic()
        for message in sorted(messages, key=lambda m: m.id):
            if self.stop.is_set():
                break
            if message.id in self.seen:
                continue
            text = message.raw_text or ""
            if message.out or not text.strip() or not message.date:
                self.remember(message.id)
                continue
            date = message.date.astimezone(UTC)
            matches = [p for p in profiles if date >= self.active_since[p.id] and profile_matches(p, text)]
            if not matches:
                self.remember(message.id)
                continue
            sender_start = monotonic()
            entity = await message.get_sender()
            sender_ms = (monotonic() - sender_start) * 1000
            if not isinstance(entity, User) or entity.bot or entity.deleted:
                self.remember(message.id)
                continue
            selected = matches[0]
            enqueue_start = monotonic()
            result = await asyncio.to_thread(
                self.db.enqueue_match, selected, self.target_chat_id, message.id, entity.id, text
            )
            self.remember(message.id)
            log.info(
                "Message matching completed",
                extra={
                    "event": "poll_match",
                    "trace_id": trace,
                    "message_id": message.id,
                    "profile_id": selected.id,
                    "result": result,
                    "sender_ms": round(sender_ms, 1),
                    "enqueue_ms": round((monotonic() - enqueue_start) * 1000, 1),
                    "message_age_ms": round((datetime.now(UTC) - date).total_seconds() * 1000, 1),
                },
            )
            if result == "no_reply":
                await self.notify(f"⚠️ Reply Pool پروفایل «{selected.name}» خالی است.")
        cycle_ms = (monotonic() - started) * 1000
        log.log(
            logging.WARNING if cycle_ms > self.interval * 1000 else logging.INFO,
            "History polling cycle completed",
            extra={
                "event": "poll_completed",
                "trace_id": trace,
                "profiles_ms": round(profiles_ms, 1),
                "cycle_ms": round(cycle_ms, 1),
                "processing_ms": round((monotonic() - processing_start) * 1000, 1),
            },
        )

    async def run(self):
        while not self.stop.is_set():
            started = monotonic()
            delay = self.interval
            try:
                await self.poll_once()
                # Missed ticks are discarded, never queued or run concurrently.
                delay = max(0.01, self.interval - (monotonic() - started))
            except FloodWaitError as exc:
                delay = max(self.interval, exc.seconds)
                log.warning(
                    "Telegram requires a polling pause",
                    extra={"event": "poll_flood_wait", "wait_seconds": delay},
                )
            except Exception as exc:
                delay = max(self.interval, 5.0)
                log.error(
                    "History polling failed",
                    extra={
                        "event": "poll_failed",
                        "error_class": type(exc).__name__,
                        "cycle_ms": round((monotonic() - started) * 1000, 1),
                    },
                )
            await self.wait(delay)
