from __future__ import annotations

import re
import unicodedata

_SPACES = re.compile(r"[\s\u00a0\u2000-\u200f\u2028-\u202f\u2060\ufeff]+")


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = text.replace("ـ", "").replace("\u200c", "").replace("\u200d", "")
    return _SPACES.sub(" ", text).strip().casefold()
