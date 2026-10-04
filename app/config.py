from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


@dataclass(frozen=True, slots=True)
class Config:
    app_env: str
    app_version: str
    database_url: str
    log_level: str
    port: int
    timezone: ZoneInfo
    timezone_name: str
    app_encryption_key: str | None
    api_id: int
    api_hash: str
    string_session: str
    bot_token: str
    admin_id: int
    target_chat_id: int
    min_send_interval: float
    default_cooldown: int
    job_poll_interval: float
    poller_lock_wait_seconds: float
    proxy: dict | None

    @classmethod
    def from_env(cls) -> Config:
        if load_dotenv:
            load_dotenv()
        required = {
            "APP_ENV": os.getenv("APP_ENV"),
            "APP_VERSION": os.getenv("APP_VERSION"),
            "DATABASE_URL": os.getenv("DATABASE_URL"),
            "TG_API_ID": os.getenv("TG_API_ID"),
            "TG_API_HASH": os.getenv("TG_API_HASH"),
            "TG_STRING_SESSION": os.getenv("TG_STRING_SESSION"),
            "CONTROL_BOT_TOKEN": os.getenv("CONTROL_BOT_TOKEN"),
            "CONTROL_ADMIN_ID": os.getenv("CONTROL_ADMIN_ID"),
            "TARGET_CHAT_ID": os.getenv("TARGET_CHAT_ID"),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        try:
            api_id = int(required["TG_API_ID"] or "")
            admin_id = int(required["CONTROL_ADMIN_ID"] or "")
            target_chat_id = int(required["TARGET_CHAT_ID"] or "")
            port = int(os.getenv("PORT", "8080"))
        except ValueError as exc:
            raise ValueError("TG_API_ID, CONTROL_ADMIN_ID, TARGET_CHAT_ID and PORT must be integers") from exc
        timezone_name = os.getenv("DEFAULT_TIMEZONE", "Asia/Tehran")
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown DEFAULT_TIMEZONE: {timezone_name}") from exc
        min_interval = float(os.getenv("MIN_SEND_INTERVAL_SECONDS", "1.0"))
        cooldown = int(os.getenv("DEFAULT_USER_COOLDOWN_SECONDS", "900"))
        job_poll_interval = float(os.getenv("JOB_POLL_INTERVAL_SECONDS", "1.0"))
        poller_lock_wait_seconds = float(os.getenv("POLLER_LOCK_WAIT_SECONDS", "120"))
        if min_interval < 0 or cooldown < 0 or job_poll_interval <= 0 or poller_lock_wait_seconds < 0:
            raise ValueError(
                "Intervals, cooldown and poller lock wait must be non-negative; "
                "job poll interval must be positive"
            )
        if not 1 <= port <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        return cls(
            app_env=required["APP_ENV"] or "",
            app_version=required["APP_VERSION"] or "",
            database_url=required["DATABASE_URL"] or "",
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            port=port,
            timezone=timezone,
            timezone_name=timezone_name,
            app_encryption_key=os.getenv("APP_ENCRYPTION_KEY") or None,
            api_id=api_id,
            api_hash=required["TG_API_HASH"] or "",
            string_session=required["TG_STRING_SESSION"] or "",
            bot_token=required["CONTROL_BOT_TOKEN"] or "",
            admin_id=admin_id,
            target_chat_id=target_chat_id,
            min_send_interval=min_interval,
            default_cooldown=cooldown,
            job_poll_interval=job_poll_interval,
            poller_lock_wait_seconds=poller_lock_wait_seconds,
            proxy=proxy_from_env(),
        )


def proxy_from_env() -> dict | None:
    raw = os.getenv("TG_PROXY_URL", "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    proxy_types = {"http": "http", "socks5": "socks5", "socks5h": "socks5", "socks4": "socks4"}
    if parsed.scheme.lower() not in proxy_types or not parsed.hostname or not parsed.port:
        raise ValueError("TG_PROXY_URL must be a valid http://, socks4:// or socks5:// URL")
    return {
        "proxy_type": proxy_types[parsed.scheme.lower()],
        "addr": parsed.hostname,
        "port": parsed.port,
        "username": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "rdns": True,
    }
