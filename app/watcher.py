from __future__ import annotations

import logging
from datetime import UTC, datetime

from telethon import events
from telethon.tl.types import User

from .db import Database
from .rules import profile_matches
from .scheduler import is_profile_active

log = logging.getLogger(__name__)


def register_watcher(client, db: Database, notify, target_chat_id: int, app_timezone, boot_time: datetime):
    @client.on(events.NewMessage(chats=target_chat_id, incoming=True))
    async def on_message(event):
        message = event.message
        if not message or not message.id or not (message.raw_text or "").strip():
            return
        date = message.date
        if date and date.astimezone(UTC) < boot_time:
            return
        if message.out:
            return
        try:
            entity = await event.get_sender()
            if not isinstance(entity, User) or entity.bot or entity.deleted or not entity.id:
                db.record_ignored(target_chat_id, message.id)
                return
            now = datetime.now(app_timezone)
            matches = [
                p for p in db.profiles() if is_profile_active(p, now) and profile_matches(p, message.raw_text)
            ]
            if not matches:
                db.record_ignored(target_chat_id, message.id)
                return
            selected = matches[0]
            result = db.enqueue_match(selected, target_chat_id, message.id, entity.id, message.raw_text)
            if result == "duplicate":
                db.log("SKIPPED_DUPLICATE", chat_id=target_chat_id, message_id=message.id)
            elif result == "no_reply":
                await notify(f"⚠️ Reply Pool پروفایل «{selected.name}» خالی است.")
        except Exception as exc:
            log.error("Failed to process update", extra={"event": "update_failed"}, exc_info=True)
            db.log(
                "PROCESSING_ERROR", chat_id=target_chat_id, message_id=message.id, detail=type(exc).__name__
            )

    return on_message
