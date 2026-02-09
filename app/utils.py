from __future__ import annotations

import re
from typing import Tuple

USERNAME_RE = re.compile(r"^@[A-Za-z0-9_]{5,32}$")


def normalize_phone(value: str) -> str:
    cleaned = re.sub(r"[\s\-()]+", "", value)
    if cleaned.startswith("+"):
        return "+" + re.sub(r"\D", "", cleaned[1:])
    return re.sub(r"\D", "", cleaned)


def parse_identifier(text: str) -> Tuple[str, str]:
    text = text.strip()
    if text.startswith("@"):
        if not USERNAME_RE.match(text):
            raise ValueError("Username non valido")
        return text, "username"

    normalized = normalize_phone(text)
    if not normalized or len(re.sub(r"\D", "", normalized)) < 6:
        raise ValueError("Telefono non valido")
    return normalized, "phone"
