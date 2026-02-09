import re
import time

TARGET_RE = re.compile(r'^(?:@[A-Za-z0-9_]{5,}|\d{5,})$')


def is_valid_target(text: str) -> bool:
    return bool(TARGET_RE.fullmatch(text.strip()))


def now_ms() -> int:
    return int(time.perf_counter() * 1000)
