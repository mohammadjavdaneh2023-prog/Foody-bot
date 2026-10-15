from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    secret_keys = (
        "DATABASE_URL",
        "TG_API_HASH",
        "TG_STRING_SESSION",
        "CONTROL_BOT_TOKEN",
        "TG_PROXY_URL",
        "APP_ENCRYPTION_KEY",
    )

    @classmethod
    def redact(cls, message: str) -> str:
        for key in cls.secret_keys:
            value = os.getenv(key)
            if value:
                message = message.replace(value, "[REDACTED]")
        return re.sub(r"(?<!\d)\+?\d{10,15}(?!\d)", "[REDACTED_NUMBER]", message)

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": "foody",
            "logger": record.name,
            "event": getattr(record, "event", "log"),
            "message": self.redact(record.getMessage()),
        }
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            payload["trace_id"] = str(trace_id)
        # Only allow operational measurements; never serialize arbitrary extras or message text.
        for key in (
            "active_profiles",
            "fetch_ms",
            "message_count",
            "message_id",
            "profile_id",
            "result",
            "sender_ms",
            "enqueue_ms",
            "message_age_ms",
            "profiles_ms",
            "processing_ms",
            "cycle_ms",
            "wait_seconds",
            "job_id",
            "queue_wait_ms",
            "send_ms",
            "notification_ms",
            "job_ms",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["error_class"] = record.exc_info[0].__name__
        elif getattr(record, "error_class", None):
            payload["error_class"] = str(record.error_class)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level, logging.INFO))
