from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class ScheduleWindow:
    weekday: int
    start_minute: int
    end_minute: int


@dataclass(slots=True)
class Profile:
    id: int
    name: str
    mode: str
    cooldown_seconds: int
    delay_min_seconds: int = 0
    delay_max_seconds: int = 0
    rule_groups: list[list[str]] = field(default_factory=list)
    not_terms: list[str] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    windows: list[ScheduleWindow] = field(default_factory=list)


@dataclass(slots=True)
class SendJob:
    id: int
    profile_id: int
    source_chat_id: int
    source_message_id: int
    sender_id: int
    source_text: str
    reply_text: str
    attempt_count: int
    available_at: datetime
