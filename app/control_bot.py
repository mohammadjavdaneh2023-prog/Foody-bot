from __future__ import annotations

import html
import logging
from collections import defaultdict
from contextlib import suppress
from time import monotonic

from telethon import Button, events

from .db import Database
from .scheduler import parse_delay_range, parse_window

DAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
log = logging.getLogger(__name__)


class ControlBot:
    def __init__(self, client, user_client, db: Database, admin_id: int, config):
        self.client, self.user_client, self.db = client, user_client, db
        self.admin_id, self.config = admin_id, config
        self.pending: dict[int, tuple[str, int, int | None]] = {}
        self.last_notices: dict[str, float] = {}

    def register(self):
        self.client.add_event_handler(self.on_message, events.NewMessage(incoming=True))
        self.client.add_event_handler(self.on_callback, events.CallbackQuery())

    async def notify(self, text: str):
        key = text[:80]
        now = monotonic()
        if now - self.last_notices.get(key, 0.0) < 300:
            return
        self.last_notices[key] = now
        with suppress(Exception):
            await self.client.send_message(self.admin_id, text)

    async def notify_sent(self, sent_text: str):
        prefix = "✅ به یک نفر پیام دادم که متن پیامش این بود:\n\n"
        continuation = "ادامهٔ متن پیام:\n\n"
        chunk_size = 3500
        first_size = chunk_size - len(prefix)
        chunks = [prefix + sent_text[:first_size]]
        remaining = sent_text[first_size:]
        while remaining:
            size = chunk_size - len(continuation)
            chunks.append(continuation + remaining[:size])
            remaining = remaining[size:]

        for client, peer, destination in (
            (self.client, self.admin_id, "control_bot"),
            (self.user_client, "me", "saved_messages"),
        ):
            for chunk in chunks:
                try:
                    await client.send_message(peer, chunk, parse_mode=None)
                except Exception as exc:
                    log.warning(
                        "Successful-send notification failed",
                        extra={
                            "event": "send_notification_failed",
                            "destination": destination,
                            "error_class": type(exc).__name__,
                        },
                    )
                    break

    def authorized(self, event) -> bool:
        return event.sender_id == self.admin_id

    async def on_message(self, event):
        if not event.is_private:
            return
        if not self.authorized(event):
            text = (event.raw_text or "").strip().lower()
            if text == "/stop":
                self.db.opt_out(event.sender_id)
                await event.respond("✅ پیام‌های خودکار FOODY برای شما متوقف شد. برای فعال‌سازی دوباره /allow")
            elif text == "/allow":
                self.db.opt_in(event.sender_id)
                await event.respond("✅ دریافت پیام‌های مرتبط FOODY دوباره مجاز شد.")
            else:
                await event.respond("این بات مدیریتی است. برای توقف پیام‌های FOODY دستور /stop را بفرستید.")
            return
        text = (event.raw_text or "").strip()
        if text in {"/start", "/menu"}:
            self.pending.pop(self.admin_id, None)
            await self.show_main(event)
            return
        if text == "/off":
            self.db.all_off()
            self.db.log("CONFIG_CHANGE", detail="All profiles OFF via /off")
            await event.respond("⛔ همهٔ پروفایل‌ها خاموش شدند.")
            await self.show_main(event)
            return
        state = self.pending.pop(self.admin_id, None)
        if not state:
            return
        action, profile_id, extra = state
        try:
            if action == "new_profile":
                if not text:
                    raise ValueError("نام خالی مجاز نیست.")
                pid = self.db.create_profile(text, self.config.default_cooldown)
                await event.respond("✅ پروفایل ساخته شد.")
                await self.show_profile(event, pid)
            elif action == "rename":
                self.db.update_profile(profile_id, name=text)
                await self.show_profile(event, profile_id)
            elif action == "cooldown":
                value = int(text)
                if value < 0:
                    raise ValueError("عدد منفی مجاز نیست.")
                self.db.update_profile(profile_id, cooldown=value)
                await self.show_profile(event, profile_id)
            elif action == "delay":
                minimum, maximum = parse_delay_range(text)
                self.db.update_delay(profile_id, minimum, maximum)
                await self.show_profile(event, profile_id)
            elif action == "group":
                terms = self._terms(text)
                self.db.add_group(profile_id, terms)
                await self.show_rules(event, profile_id)
            elif action == "term":
                if not text:
                    raise ValueError("عبارت خالی مجاز نیست.")
                self.db.add_term(int(extra), text)
                await self.show_rules(event, profile_id)
            elif action == "not":
                terms = self._terms(text)
                self.db.add_not_terms(profile_id, terms)
                await self.show_not(event, profile_id)
            elif action == "reply":
                if not text:
                    raise ValueError("پیام خالی مجاز نیست.")
                self.db.add_reply(profile_id, text)
                await self.show_replies(event, profile_id)
            elif action == "window":
                start, end = parse_window(text)
                self.db.add_window(profile_id, int(extra), start, end)
                await self.show_day(event, profile_id, int(extra))
            self.db.log("CONFIG_CHANGE", profile_id=profile_id, detail=action)
        except (ValueError, TypeError) as exc:
            self.pending[self.admin_id] = state
            await event.respond(f"❌ {exc}\nدوباره ارسال کنید یا /menu را بزنید.")

    @staticmethod
    def _terms(text):
        terms = [x.strip() for x in text.split("|") if x.strip()]
        if not terms:
            raise ValueError("حداقل یک عبارت لازم است.")
        return terms

    async def on_callback(self, event):
        if not self.authorized(event):
            await event.answer("Unauthorized", alert=True)
            return
        await event.answer()
        parts = event.data.decode().split(":")
        action = parts[0]
        pid = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        if action == "main":
            await self.show_main(event)
        elif action == "profiles":
            await self.show_profiles(event)
        elif action == "profile":
            await self.show_profile(event, pid)
        elif action == "new":
            self.pending[self.admin_id] = ("new_profile", 0, None)
            await event.respond("نام پروفایل را بفرستید:")
        elif action == "mode":
            self.db.update_profile(pid, mode=parts[2])
            self.db.log("CONFIG_CHANGE", pid, detail=f"mode={parts[2]}")
            await self.show_profile(event, pid)
        elif action == "rules":
            await self.show_rules(event, pid)
        elif action == "addgroup":
            self.pending[self.admin_id] = ("group", pid, None)
            await event.respond("عبارت‌های OR را با | جدا کنید:")
        elif action == "delgroup":
            self.db.delete_group(int(parts[2]))
            await self.show_rules(event, pid)
        elif action == "addterm":
            self.pending[self.admin_id] = ("term", pid, int(parts[2]))
            await event.respond("عبارت جدید این گروه را بفرستید:")
        elif action == "delterm":
            self.db.delete_term(int(parts[2]))
            await self.show_rules(event, pid)
        elif action == "nots":
            await self.show_not(event, pid)
        elif action == "addnot":
            self.pending[self.admin_id] = ("not", pid, None)
            await event.respond("عبارت‌های NOT را با | جدا کنید:")
        elif action == "replies":
            await self.show_replies(event, pid)
        elif action == "addreply":
            self.pending[self.admin_id] = ("reply", pid, None)
            await event.respond("متن کامل پاسخ را بفرستید:")
        elif action == "delitem":
            self.db.delete_item(parts[2], int(parts[3]))
            await (self.show_not(event, pid) if parts[2] == "not_terms" else self.show_replies(event, pid))
        elif action == "schedule":
            await self.show_schedule(event, pid)
        elif action == "day":
            await self.show_day(event, pid, int(parts[2]))
        elif action == "addwindow":
            self.pending[self.admin_id] = ("window", pid, int(parts[2]))
            await event.respond("بازه را مانند 10:30-13:30 بفرستید:")
        elif action == "delwindow":
            self.db.delete_item("schedule_windows", int(parts[3]))
            await self.show_day(event, pid, int(parts[2]))
        elif action in {"rename", "cooldown"}:
            self.pending[self.admin_id] = (action, pid, None)
            await event.respond("مقدار جدید را بفرستید:")
        elif action == "delay":
            self.pending[self.admin_id] = (action, pid, None)
            await event.respond("بازهٔ تأخیر را مانند 2-10 بفرستید. برای خاموش‌کردن 0-0:")
        elif action == "deleteask":
            await self._edit(
                event,
                "پروفایل حذف شود؟",
                [[Button.inline("✅ بله", f"delete:{pid}"), Button.inline("↩️ خیر", f"profile:{pid}")]],
            )
        elif action == "delete":
            self.db.delete_profile(pid)
            await self.show_profiles(event)
        elif action == "offask":
            await self._edit(
                event,
                "همهٔ پروفایل‌ها خاموش شوند؟",
                [[Button.inline("⛔ تأیید", "alloff"), Button.inline("↩️ برگشت", "main")]],
            )
        elif action == "alloff":
            self.db.all_off()
            self.db.log("CONFIG_CHANGE", detail="All profiles OFF")
            await self.show_main(event)
        elif action == "status":
            await self.show_status(event)
        elif action == "logs":
            await self.show_logs(event)

    async def _edit(self, event, text, buttons):
        if getattr(event, "data", None) is not None:
            await event.edit(text, buttons=buttons)
        else:
            await event.respond(text, buttons=buttons)

    async def show_main(self, event):
        await self._edit(
            event,
            "🍽 FOODY",
            [
                [Button.inline("🎯 Profiles", "profiles"), Button.inline("📊 Status", "status")],
                [Button.inline("🧾 Recent Logs", "logs"), Button.inline("⛔ All Off", "offask")],
            ],
        )

    async def show_profiles(self, event):
        buttons = [[Button.inline(f"{p.name} | {p.mode}", f"profile:{p.id}")] for p in self.db.profiles()]
        buttons += [[Button.inline("➕ New Profile", "new")], [Button.inline("↩️ Back", "main")]]
        await self._edit(event, "🎯 پروفایل‌ها", buttons)

    async def show_profile(self, event, pid):
        p = self.db.profile(pid)
        if not p:
            await self.show_profiles(event)
            return
        buttons = [
            [Button.inline(x, f"mode:{pid}:{x}") for x in ("OFF", "ON", "SCHEDULE")],
            [Button.inline("Rules", f"rules:{pid}"), Button.inline("NOT Terms", f"nots:{pid}")],
            [Button.inline("Schedule", f"schedule:{pid}"), Button.inline("Reply Pool", f"replies:{pid}")],
            [Button.inline("Cooldown", f"cooldown:{pid}"), Button.inline("Human Delay", f"delay:{pid}")],
            [Button.inline("Rename", f"rename:{pid}"), Button.inline("🗑 Delete", f"deleteask:{pid}")],
            [Button.inline("↩️ Back", "profiles")],
        ]
        await self._edit(
            event,
            f"<b>{html.escape(p.name)}</b>\n"
            f"Mode: {p.mode}\n"
            f"Cooldown: {p.cooldown_seconds}s\n"
            f"Human delay: {p.delay_min_seconds}-{p.delay_max_seconds}s",
            buttons,
        )

    async def show_rules(self, event, pid):
        rows = self.db.group_rows(pid)
        text = "Rules\n" + "\n".join(f"{i + 1}. {' | '.join(t)}" for i, (_, t) in enumerate(rows))
        buttons = []
        for i, (gid, _) in enumerate(rows):
            buttons.append(
                [
                    Button.inline(f"➕ Term G{i + 1}", f"addterm:{pid}:{gid}"),
                    Button.inline(f"🗑 Group {i + 1}", f"delgroup:{pid}:{gid}"),
                ]
            )
            buttons.extend(
                [
                    [Button.inline(f"🗑 G{i + 1}: {r['term'][:24]}", f"delterm:{pid}:{r['id']}")]
                    for r in self.db.term_rows(gid)
                ]
            )
        buttons += [
            [Button.inline("➕ Add AND Group", f"addgroup:{pid}")],
            [Button.inline("↩️ Back", f"profile:{pid}")],
        ]
        await self._edit(event, text, buttons)

    async def show_not(self, event, pid):
        rows = self.db.list_items("not_terms", pid)
        buttons = [
            [Button.inline(f"🗑 {r['value'][:30]}", f"delitem:{pid}:not_terms:{r['id']}")] for r in rows
        ]
        buttons += [
            [Button.inline("➕ Add NOT", f"addnot:{pid}")],
            [Button.inline("↩️ Back", f"profile:{pid}")],
        ]
        await self._edit(event, "NOT Terms", buttons)

    async def show_replies(self, event, pid):
        rows = self.db.list_items("reply_messages", pid)
        buttons = [
            [Button.inline(f"🗑 {r['value'][:30]}", f"delitem:{pid}:reply_messages:{r['id']}")] for r in rows
        ]
        buttons += [
            [Button.inline("➕ Add Reply", f"addreply:{pid}")],
            [Button.inline("↩️ Back", f"profile:{pid}")],
        ]
        await self._edit(event, "Reply Pool", buttons)

    async def show_schedule(self, event, pid):
        buttons = [
            [Button.inline(DAYS[i], f"day:{pid}:{i}") for i in range(a, min(a + 2, 7))]
            for a in range(0, 7, 2)
        ]
        buttons.append([Button.inline("↩️ Back", f"profile:{pid}")])
        await self._edit(event, "روز را انتخاب کنید:", buttons)

    async def show_day(self, event, pid, day):
        rows = self.db.windows(pid, day)

        def fmt(minutes):
            return f"{minutes // 60:02d}:{minutes % 60:02d}"

        buttons = [
            [
                Button.inline(
                    f"🗑 {fmt(r['start_minute'])}-{fmt(r['end_minute'])}", f"delwindow:{pid}:{day}:{r['id']}"
                )
            ]
            for r in rows
        ]
        buttons += [
            [Button.inline("➕ Add Window", f"addwindow:{pid}:{day}")],
            [Button.inline("↩️ Days", f"schedule:{pid}")],
        ]
        await self._edit(event, DAYS[day], buttons)

    async def show_status(self, event):
        ps = self.db.profiles()
        counts = defaultdict(int)
        for p in ps:
            counts[p.mode] += 1
        match = self.db.last_event("MATCH")
        sent = self.db.last_event("SENT")
        err = self.db.last_event("SEND_ERROR")

        def line(row):
            return row["created_at"].isoformat() if row else "-"

        queue = self.db.queue_counts()
        connection = "Connected" if self.user_client.is_connected() else "Disconnected"
        text = (
            f"User client: {connection}\n"
            "Control bot: Connected\n"
            f"Target chat: {self.config.target_chat_id}\n"
            f"Timezone: {self.config.timezone_name}\n"
            f"Profiles — ON: {counts['ON']}, SCHEDULE: {counts['SCHEDULE']}, OFF: {counts['OFF']}\n"
            f"Queue — pending: {queue.get('pending', 0)}, ambiguous: {queue.get('ambiguous', 0)}\n"
            f"Last match: {line(match)}\n"
            f"Last sent: {line(sent)}\n"
            f"Last error: {line(err)}\n"
            "DB: PostgreSQL OK"
        )
        await self._edit(event, text, [[Button.inline("↩️ Back", "main")]])

    async def show_logs(self, event):
        rows = self.db.recent_logs()
        text = "Recent Logs\n" + "\n".join(
            f"{r['created_at'].isoformat()[:19]} {r['event_type']} {r['detail'] or ''}" for r in rows
        )
        await self._edit(event, text[:4000], [[Button.inline("↩️ Back", "main")]])
