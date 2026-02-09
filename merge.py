import re
from typing import Dict, List

BOT_TAGS = (r'@Botfindinformation_bot', r'@WOW_MYAI_BOT')


def _clean_text(text: str) -> str:
    cleaned = text
    for bot_tag in BOT_TAGS:
        cleaned = re.sub(bot_tag, '', cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r'(?im)^.*powered by.*$', '', cleaned)
    cleaned = re.sub(r'(?im)^.*join\s+channel.*$', '', cleaned)
    cleaned = re.sub(r'https?://t\.me/\S+', '', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def _dedupe_lines(text: str) -> List[str]:
    seen = set()
    lines: List[str] = []

    for raw in text.splitlines():
        line = raw.strip('•- \t')
        if not line:
            continue

        key = re.sub(r'\s+', ' ', line).strip().lower()
        if key in seen:
            continue

        seen.add(key)
        lines.append(line)

    return lines


def _emoji(line: str) -> str:
    lower = line.lower()
    if 'name' in lower or 'username' in lower:
        return '👤'
    if 'phone' in lower or re.search(r'\+?\d{7,}', line):
        return '📞'
    if 'id' in lower:
        return '🆔'
    if 'email' in lower:
        return '📧'
    if 'location' in lower or 'address' in lower:
        return '📍'
    return '📌'


def build_test1_output(raw_responses: Dict[str, str]) -> str:
    merged_raw = '\n'.join(raw_responses.values())
    cleaned = _clean_text(merged_raw)
    unique_lines = _dedupe_lines(cleaned)

    if not unique_lines:
        return '🧪 *Test1*\n\n⚠️ Nessun dato utile trovato.'

    body = '\n'.join(f'{_emoji(line)} {line}' for line in unique_lines)
    return (
        '🧪 *Test1*\n'
        '━━━━━━━━━━━━━━\n'
        '📋 *Risultati Ricerca*\n\n'
        f'{body}'
    )
