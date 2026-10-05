from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from telethon.errors import FloodWaitError, RPCError

from .db import Database
from .models import SendJob

log = logging.getLogger(__name__)


class Sender:
    def __init__(self, client, db: Database, min_interval: float, poll_interval: float, notify, notify_sent):
        self.client = client
        self.db = db
        self.min_interval = min_interval
        self.poll_interval = poll_interval
        self.notify = notify
        self.notify_sent = notify_sent
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        while not self.stop_event.is_set():
            job = self.db.claim_next_job()
            if job is None:
                with suppress(TimeoutError):
                    await asyncio.wait_for(self.stop_event.wait(), timeout=self.poll_interval)
                continue
            try:
                await self._send(job)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.error("Sender worker failure", extra={"event": "sender_worker_failed"}, exc_info=True)
                with suppress(Exception):
                    self.db.finish_job(job, "ambiguous", "WorkerFailure")

    async def _send(self, job: SendJob) -> None:
        profile = self.db.profile(job.profile_id)
        if not profile or profile.mode == "OFF":
            self.db.finish_job(job, "cancelled", "ProfileInactive")
            return
        if self.db.is_opted_out(job.sender_id):
            self.db.finish_job(job, "cancelled", "RecipientOptedOut")
            return
        if self.db.in_cooldown(profile.id, job.sender_id, profile.cooldown_seconds):
            self.db.finish_job(job, "cancelled", "CooldownActive")
            return
        wait = self.db.global_send_wait(self.min_interval)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            sent_message = await self.client.send_message(job.sender_id, job.reply_text)
        except FloodWaitError as exc:
            self.db.defer_job(job.id, exc.seconds, type(exc).__name__)
            await self.notify(f"⚠️ Telegram FloodWait: {exc.seconds} seconds")
        except RPCError as exc:
            self.db.finish_job(job, "failed", type(exc).__name__)
            log.warning("Telegram rejected an outbound message", extra={"event": "send_rejected"})
            await self.notify(f"⚠️ DM failed: {type(exc).__name__}")
        except asyncio.CancelledError:
            self.db.finish_job(job, "ambiguous", "ShutdownDuringSend")
            raise
        except Exception as exc:
            self.db.finish_job(job, "ambiguous", type(exc).__name__)
            log.error("Outbound message has an ambiguous result", extra={"event": "send_ambiguous"})
            await self.notify("⚠️ نتیجهٔ یک ارسال نامشخص است؛ ارسال خودکار تکرار نشد.")
        else:
            self.db.finish_job(job, "sent")
            sent_text = getattr(sent_message, "raw_text", None) or job.reply_text
            try:
                await self.notify_sent(job.source_text, sent_text)
            except Exception as exc:
                log.warning(
                    "Successful-send notification failed",
                    extra={"event": "send_notification_failed", "error_class": type(exc).__name__},
                )

    async def stop(self) -> None:
        self.stop_event.set()
