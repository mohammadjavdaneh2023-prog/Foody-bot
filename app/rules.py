from __future__ import annotations

from .models import Profile
from .normalize import normalize_text


def profile_matches(profile: Profile, text: str) -> bool:
    if not profile.rule_groups or any(not group for group in profile.rule_groups):
        return False
    normalized = normalize_text(text)
    if any(term and term in normalized for term in profile.not_terms):
        return False
    return all(any(term and term in normalized for term in group) for group in profile.rule_groups)
