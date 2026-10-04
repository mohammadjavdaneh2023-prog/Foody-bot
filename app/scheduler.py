from __future__ import annotations

from datetime import datetime

from .models import Profile


def is_profile_active(profile: Profile, now: datetime) -> bool:
    if profile.mode == "OFF":
        return False
    if profile.mode == "ON":
        return True
    if profile.mode != "SCHEDULE":
        return False
    minute = now.hour * 60 + now.minute
    return any(
        window.weekday == now.weekday() and window.start_minute <= minute < window.end_minute
        for window in profile.windows
    )


def parse_window(value: str) -> tuple[int, int]:
    try:
        start, end = (part.strip() for part in value.split("-", 1))
        sh, sm = (int(x) for x in start.split(":"))
        eh, em = (int(x) for x in end.split(":"))
    except (ValueError, TypeError) as exc:
        raise ValueError("بازه باید مانند 10:30-13:30 باشد.") from exc
    if not (0 <= sh <= 23 and 0 <= eh <= 23 and 0 <= sm <= 59 and 0 <= em <= 59):
        raise ValueError("ساعت یا دقیقه معتبر نیست.")
    start_minute, end_minute = sh * 60 + sm, eh * 60 + em
    if start_minute >= end_minute:
        raise ValueError("ساعت پایان باید بعد از شروع و در همان روز باشد.")
    return start_minute, end_minute


def parse_delay_range(value: str) -> tuple[int, int]:
    try:
        parts = [part.strip() for part in value.split("-", 1)]
        minimum = int(parts[0])
        maximum = int(parts[1]) if len(parts) == 2 else minimum
    except (ValueError, TypeError) as exc:
        raise ValueError("بازه را مانند 2-10 وارد کنید.") from exc
    if minimum < 0 or maximum < minimum:
        raise ValueError("بازه باید مثبت باشد و مقدار دوم از اول کمتر نباشد.")
    if maximum > 300:
        raise ValueError("حداکثر تأخیر مجاز 300 ثانیه است.")
    return minimum, maximum
