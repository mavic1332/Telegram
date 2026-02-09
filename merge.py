import re
from typing import List, Optional

from models import RawBotResponses, SearchResult

CYRILLIC_RE = re.compile(r'[\u0400-\u04FF]+')
ID_AFTER_LABEL_RE = re.compile(r'ID\s*:\s*(\d+)', flags=re.IGNORECASE)
PHONE_AFTER_LABEL_RE = re.compile(r'Телефон\s*:\s*([^\n\r]+)', flags=re.IGNORECASE)
USERNAME_RE = re.compile(r'@[A-Za-z0-9_]{3,}')
DIGITS_RE = re.compile(r'\d+')
MONTH_MAP_IT = {
    'january': 'Gennaio',
    'february': 'Febbraio',
    'march': 'Marzo',
    'april': 'Aprile',
    'may': 'Maggio',
    'june': 'Giugno',
    'july': 'Luglio',
    'august': 'Agosto',
    'september': 'Settembre',
    'october': 'Ottobre',
    'november': 'Novembre',
    'december': 'Dicembre',
}


def _translate_months(text: str) -> str:
    out = text
    for en, it in MONTH_MAP_IT.items():
        out = re.sub(rf'\b{en}\b', it, out, flags=re.IGNORECASE)
    return out


def _strip_noise(text: str) -> str:
    cleaned = text or ''
    for pat in (
        r'@Botfindinformation_bot',
        r'@WOW_MYAI_BOT',
        r'@UniversalSearch',
        r'fake\s+generator\s+bot',
        r'(?im)^\s*by\s+.*$',
        r'(?im)^.*powered\s+by.*$',
        r'(?im)^.*join\s+channel.*$',
        r'https?://t\.me/\S+',
    ):
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
    return re.sub(r'\n{3,}', '\n\n', cleaned).strip()


def _section_lines(text: str, start_anchor: str, end_anchor: str) -> List[str]:
    start = text.find(start_anchor)
    if start == -1:
        return []
    body = text[start + len(start_anchor):]
    end = body.find(end_anchor)
    if end != -1:
        body = body[:end]
    return [ln.strip('•- \t') for ln in body.splitlines() if ln.strip()]


def _extract_bot_a(raw: str) -> tuple[Optional[str], Optional[str], List[str], List[str]]:
    text = _strip_noise(raw)

    id_match = ID_AFTER_LABEL_RE.search(text)
    id_value = id_match.group(1) if id_match else None

    phone_value = None
    phone_match = PHONE_AFTER_LABEL_RE.search(text)
    if phone_match:
        digit_candidates = [d for d in DIGITS_RE.findall(phone_match.group(1)) if len(d) > 10]
        phone_value = digit_candidates[0] if digit_candidates else None

    history = _section_lines(text, 'История изменения имени', 'Группы')
    groups_section = _section_lines(text, 'Группы', 'Контактные связи')
    groups = USERNAME_RE.findall('\n'.join(groups_section))

    return id_value, phone_value, history, groups


def _extract_bot_b(raw: str) -> tuple[Optional[str], Optional[str], List[str]]:
    text = _strip_noise(raw)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    id_value = None
    reg_value = None
    history: List[str] = []

    for idx, line in enumerate(lines):
        lower = line.lower()

        if lower.startswith('search by telegram id') and not id_value:
            nums = DIGITS_RE.findall(line)
            if nums:
                id_value = nums[-1]
            continue

        if 'registered' in lower and reg_value is None:
            if idx + 1 < len(lines):
                reg_value = _translate_months(lines[idx + 1])
            else:
                inline = re.sub(r'(?i)^.*registered\s*[:\]]?\s*', '', line).strip()
                reg_value = _translate_months(inline) if inline else None
            continue

        history.append(line)

    return id_value, reg_value, history


def _clean_visible(text: str) -> str:
    s = CYRILLIC_RE.sub('', text)
    s = re.sub(r'\s{2,}', ' ', s).strip(' :-')
    return s.strip()


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        value = _clean_visible(item)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def build_report(raw: RawBotResponses, elapsed_ms: int, target: str) -> SearchResult:
    id_a, phone_a, history_a, groups_a = _extract_bot_a(raw.botfindinformation)
    id_b, reg_b, history_b = _extract_bot_b(raw.wow_myai)

    final_id = id_a or id_b or 'N/D'
    final_reg = _clean_visible(reg_b) if reg_b else 'N/D'
    final_phone = _clean_visible(phone_a) if phone_a else 'N/D'

    storic_lines = _dedupe(history_a + history_b + groups_a)[:12]
    data_items: List[str] = []
    if groups_a:
        data_items.append(f"Gruppi: {', '.join(_dedupe(groups_a))}")
    data_value = _clean_visible(' | '.join(data_items)) if data_items else 'N/D'

    lines = [
        '✅ Tipo risultato: Aggregato Test1',
        f'👤 Identificatore: {target}',
        f'🆔 ID: {final_id}',
        f'🗓️ Registrazione: {final_reg}',
        f'📞 Telefono: {final_phone}',
        f'📊 Dati: {data_value}',
    ]

    if raw.bot_a_retry_after:
        lines.append(f'⏳ Bot A temporaneamente occupato. Riprova tra {raw.bot_a_retry_after}')
    elif raw.bot_a_wait_until:
        lines.append(f'⚠️ Bot A non disponibile fino alle {raw.bot_a_wait_until}')

    lines.append('🕒 Storico:')
    lines.extend([f'• {item}' for item in storic_lines] or ['• Nessun dato disponibile'])
    lines.append(f'\n⏱️ Tempo elaborazione: {elapsed_ms} ms')

    status = '+' if (final_id != 'N/D' or final_phone != 'N/D' or storic_lines) else '-'
    if raw.bot_a_retry_after or raw.bot_a_wait_until:
        status = '!' if status == '-' else status

    return SearchResult(
        target=target,
        lines=[_clean_visible(ln) for ln in lines],
        elapsed_ms=elapsed_ms,
        status=status,
        bot_a_seconds=raw.bot_a_seconds,
        bot_b_seconds=raw.bot_b_seconds,
    )
