import logging
import re
import time
from datetime import datetime

TARGET_RE = re.compile(r'^(?:@[A-Za-z0-9_]{5,}|\d{5,})$')


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format='%(message)s')


def ts_hms() -> str:
    return datetime.now().strftime('%H:%M:%S')


def now_ms() -> int:
    return int(time.perf_counter() * 1000)


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def is_valid_target(text: str) -> bool:
    return bool(TARGET_RE.fullmatch(text.strip()))
