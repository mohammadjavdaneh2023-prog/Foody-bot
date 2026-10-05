from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime

from telethon import events
from telethon.tl.types import User

from .db import Database
from .rules import profile_matches
from .scheduler import is_profile_active

log = logging.getLogger(__name__)

RECONCILE_INTERVAL_SECONDS = 5.0


async def process_message(
    message,
    get_sender,
    db: Database,
    notify,
    target_chat_id: int,
    app_timezone,
    boot_time: datetime,
    source: str,
) -> bool:
    if not message or not message.id or not (message.raw_text or "").strip():
        return True
    if message.date and message.date.astimezone(UTC) < boot_time:
        return True
    if message.out:
        return True

    try:
        entity = await get_sender()
        if not isinstance(entity, User) or entity.bot or entity.deleted or not entity.id:
            db.record_ignored(target_chat_id, message.id)
            return True

        now = datetime.now(app_timezone)
        matches = [
            profile
            for profile in db.profiles()
            if is_profile_active(profile, now) and profile_matches(profile, message.raw_text)
        ]
        if not matches:
            db.record_ignored(target_chat_id, message.id)
            return True

        selected = matches[0]
        result = db.enqueue_match(selected, target_chat_id, message.id, entity.id, message.raw_text)
        if result == "duplicate":
            db.log("SKIPPED_DUPLICATE", chat_id=target_chat_id, message_id=message.id)
        elif result == "no_reply":
            await notify(f"⚠️ Reply Pool پروفایل «{selected.name}» خالی است.")

        age_ms = (
            max(0, int((datetime.now(UTC) - message.date.astimezone(UTC)).total_seconds() * 1000))
            if message.date
            else -1
        )
        log.info(
            "Matched group message (source=%s, message_age_ms=%s)",
            source,
            age_ms,
            extra={"event": "group_message_matched"},
        )
        return True
    except Exception as exc:
        log.error("Failed to process update", extra={"event": "update_failed"}, exc_info=True)
        db.log("PROCESSING_ERROR", chat_id=target_chat_id, message_id=message.id, detail=type(exc).__name__)
        return False


class NewMessageReconciler:
    """Fetch messages newer than the startup cursor as a fallback for delayed MTProto updates."""

    def __init__(self, client, target_chat_id: int, handler, interval: float = RECONCILE_INTERVAL_SECONDS):
        self.client = client
        self.target_chat_id = target_chat_id
        self.handler = handler
        self.interval = interval
        self.last_message_id = 0

    async def initialize(self) -> None:
        latest = await self.client.get_messages(self.target_chat_id, limit=1)
        self.last_message_id = max((message.id for message in latest if message and message.id), default=0)

    async def scan_once(self) -> int:
        processed = 0
        async for message in self.client.iter_messages(
            self.target_chat_id,
            min_id=self.last_message_id,
            reverse=True,
        ):
            if not message or not message.id or message.id <= self.last_message_id:
                continue
            if not await self.handler(message):
                break
            self.last_message_id = message.id
            processed += 1
        return processed

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(
                    "Recent-message reconciliation failed",
                    extra={"event": "update_reconciliation_failed", "error_class": type(exc).__name__},
                )
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval)


def register_watcher(
    client,
    db: Database,
    notify,
    target_chat_id: int,
    app_timezone,
    boot_time: datetime,
):
    async def handle_message(message, get_sender, source: str) -> bool:
        return await process_message(
            message,
            get_sender,
            db,
            notify,
            target_chat_id,
            app_timezone,
            boot_time,
            source,
        )

    @client.on(events.NewMessage(chats=target_chat_id, incoming=True))
    async def on_message(event):
        await handle_message(event.message, event.get_sender, "live")

    async def reconcile_message(message) -> bool:
        return await handle_message(message, message.get_sender, "reconcile")

    return on_message, reconcile_message
