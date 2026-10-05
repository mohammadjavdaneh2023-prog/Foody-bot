from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress
from datetime import UTC, datetime
from time import monotonic

from telethon import TelegramClient
from telethon.sessions import StringSession

from .config import Config
from .control_bot import ControlBot
from .db import Database
from .health import HealthState, start_health_server
from .logging_setup import setup_logging
from .migrations import migrate
from .sender import Sender
from .watcher import register_watcher

log = logging.getLogger(__name__)


async def acquire_poller_lock_with_wait(
    db: Database,
    stop: asyncio.Event,
    timeout: float,
    retry_interval: float = 1.0,
) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while not stop.is_set():
        if db.acquire_poller_lock():
            return True
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return False
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=min(retry_interval, remaining))
    return False


async def maintenance_loop(db: Database, stop: asyncio.Event) -> None:
    last_cleanup = monotonic()
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except TimeoutError:
            if not db.poller_lock_alive():
                log.critical("Polling lock connection was lost", extra={"event": "poller_lock_lost"})
                stop.set()
                return
            if monotonic() - last_cleanup >= 86400:
                db.cleanup()
                last_cleanup = monotonic()


async def main() -> None:
    config = Config.from_env()
    setup_logging(config.log_level)
    state = HealthState(config.app_version)
    health_server = await start_health_server(state, config.port)
    db: Database | None = None
    user = TelegramClient(
        StringSession(config.string_session), config.api_id, config.api_hash, proxy=config.proxy
    )
    bot = TelegramClient(None, config.api_id, config.api_hash, proxy=config.proxy)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop.set)
    sender: Sender | None = None
    sender_task: asyncio.Task | None = None
    cleanup_task: asyncio.Task | None = None
    try:
        applied = migrate(config.database_url)
        state.migrations_ready = True
        db = Database(config.database_url)
        state.db = db
        db.cleanup()
        lock_acquired = await acquire_poller_lock_with_wait(
            db,
            stop,
            config.poller_lock_wait_seconds,
        )
        if not lock_acquired:
            if stop.is_set():
                return
            raise RuntimeError("Telegram polling lock was not released before the startup timeout")
        ambiguous = db.recover_inflight()
        if ambiguous:
            log.warning(
                "Recovered in-flight jobs as ambiguous",
                extra={"event": "jobs_recovered_ambiguous"},
            )
        await user.connect()
        if not await user.is_user_authorized():
            raise RuntimeError("TG_STRING_SESSION is invalid or unauthorized")
        await user.get_entity(config.target_chat_id)
        await bot.start(bot_token=config.bot_token)
        control = ControlBot(bot, user, db, config.admin_id, config)
        control.register()
        sender = Sender(
            user,
            db,
            config.min_send_interval,
            config.job_poll_interval,
            control.notify,
            control.notify_sent,
        )
        register_watcher(
            user,
            db,
            control.notify,
            config.target_chat_id,
            config.timezone,
            datetime.now(UTC),
        )
        sender_task = asyncio.create_task(sender.run(), name="durable-sender")
        cleanup_task = asyncio.create_task(maintenance_loop(db, stop), name="maintenance")
        state.telegram_ready = True
        db.log("STARTUP", detail=f"version={config.app_version}")
        log.info(
            "FOODY is ready",
            extra={"event": "service_ready", "trace_id": config.app_version},
        )
        if applied:
            log.info("Database migrations applied", extra={"event": "migrations_applied"})
        await stop.wait()
    finally:
        state.shutting_down = True
        state.telegram_ready = False
        if sender:
            await sender.stop()
        if sender_task:
            try:
                await asyncio.wait_for(sender_task, timeout=25)
            except TimeoutError:
                sender_task.cancel()
                await asyncio.gather(sender_task, return_exceptions=True)
        if cleanup_task:
            cleanup_task.cancel()
            await asyncio.gather(cleanup_task, return_exceptions=True)
        if db:
            db.log("SHUTDOWN")
        await user.disconnect()
        await bot.disconnect()
        if db:
            db.close()
        health_server.close()
        await health_server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        logging.getLogger(__name__).critical(
            "FOODY could not start",
            extra={"event": "startup_failed", "error_class": type(exc).__name__},
        )
        raise SystemExit("FOODY could not start; check configuration and structured logs") from None
