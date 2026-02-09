from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from typing import Optional

from app.config import settings


class RateLimiter:
    def __init__(self, cooldown_seconds: int = 3):
        self.cooldown_seconds = cooldown_seconds
        self._last_seen = defaultdict(float)

    def allow(self, chat_id: int) -> bool:
        now = time.monotonic()
        if now - self._last_seen[chat_id] < self.cooldown_seconds:
            return False
        self._last_seen[chat_id] = now
        return True


def is_chat_allowed(chat_id: int) -> bool:
    allowed = settings.allowed_chat_ids_list
    return not allowed or chat_id in allowed


def mask_identifier(value: Optional[str]) -> str:
    if not value:
        return "***"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value)-4)}{value[-2:]}"


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
