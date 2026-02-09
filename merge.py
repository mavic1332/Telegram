import re
from typing import Optional

from models import RawBotResponses, SearchResult

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
CYRILLIC_RE = re.compile(r'[\u0400-\u04FF]+')


def _strip_noise(text: str) -> str:
    cleaned = text or ''
    for pattern in (
        r'@Botfindinformation_bot',
        r'@WOW_MYAI_BOT',
        r'@UniversalSearch',
        r'fake\s+generator\s+bot',
        r'(?im)^\s*by\s+.*$',
        r'(?im)^.*powered\s+by.*$',
        r'(?im)^.*join\s+channel.*$',
        r'https?://t\.me/\S+',
    ):
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _to_it_month(text: str) -> str:
    out = text
    for en, it in MONTH_MAP_IT.items():
        out = re.sub(rf'\b{en}\b', it, out, flags=re.IGNORECASE)
    return out


def _clean_visible(text: str) -> str:
    text = CYRILLIC_RE.sub('', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip(' :-\n\t')


def _extract_bot_b_id(text: str) -> Optional[str]:
    match = re.search(r'(?im)^\s*Search\s+by\s+Telegram\s+ID\s+.*?(\d+)\s*$', text)
    if not match:
        return None
    digits = re.sub(r'\D', '', match.group(1))
    return digits if digits else None


def _extract_bot_b_registered(text: str) -> Optional[str]:
    key_match = re.search(r'(?im)^\s*🔑\s*([^\n\r🤖]+)', text)
    if key_match:
        value = key_match.group(1).strip()
        if value and 'search by telegram id' not in value.lower():
            return _to_it_month(value)

    reg_inline = re.search(r'(?im)^\s*Registered\s*[:\-]?\s*([^\n\r🤖]+)', text)
    if reg_inline:
        value = reg_inline.group(1).strip()
        if value and 'search by telegram id' not in value.lower():
            return _to_it_month(value)

    reg_next = re.search(r'(?is)Registered\s*\n\s*([^\n\r🤖]+)', text)
    if reg_next:
        value = reg_next.group(1).strip()
        if value and 'search by telegram id' not in value.lower():
            return _to_it_month(value)

    return None


def _extract_bot_b_bots_summary(text: str) -> list[str]:
    match = re.search(r'(?is)🤖\s*Bots\s*(.*)$', text)
    if not match:
        return []
    lines = [ln.strip('•- \t>') for ln in re.split(r'\r?\n', match.group(1)) if ln.strip()]
    out: list[str] = []
    for line in lines:
        if ':' in line:
            out.append(line)
    return out


def _extract_blockquote_usernames(text: str) -> list[str]:
    quote_lines = re.findall(r'(?im)^\s*>\s*(.+)$', text)
    return re.findall(r'@[A-Za-z0-9_]{3,}', '\n'.join(quote_lines))


def _extract_bot_a_phone(text: str) -> Optional[str]:
    line_match = re.search(r'(?im)^.*(?:Телефон:|📞)\s*([^\n\r]+)$', text)
    if not line_match:
        return None
    candidates = re.findall(r'\d{10,13}', line_match.group(1))
    return candidates[0] if candidates else None


def _extract_bot_a_id(text: str) -> Optional[str]:
    match = re.search(r'(?im)\bID\s*:\s*(\d+)', text)
    if not match:
        return None
    digits = re.sub(r'\D', '', match.group(1))
    return digits if digits else None


def _extract_bot_a_history(text: str) -> list[str]:
    match = re.search(r'(?is)История\s+изменения\s+имени\s*:\s*(.*?)\s*👥\s*Группы\s*:', text)
    if not match:
        return []
    block = match.group(1)
    return [ln.strip('•- \t>') for ln in re.split(r'\r?\n', block) if ln.strip()]


def _extract_bot_a_groups(text: str) -> list[str]:
    match = re.search(r'(?is)👥\s*Группы\s*:\s*(.*?)(?:\n\s*(?:📖|🕓|📞|💬|$))', text)
    if not match:
        return []
    block = match.group(1)
    lines = [ln.strip('> \t') for ln in re.split(r'\r?\n', block) if ln.strip()]
    return re.findall(r'@[A-Za-z0-9_]{3,}', '\n'.join(lines))


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out: list[str] = []
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
    bot_a = _strip_noise(raw.botfindinformation)
    bot_b = _strip_noise(raw.wow_myai)

    final_id = _extract_bot_a_id(bot_a) or _extract_bot_b_id(bot_b) or 'N/D'
    final_phone = _extract_bot_a_phone(bot_a) or 'N/D'
    final_registration = _extract_bot_b_registered(bot_b) or 'N/D'

    groups = _extract_bot_a_groups(bot_a)
    quote_users = _extract_blockquote_usernames(bot_a + '\n' + bot_b)
    bot_b_summary = _extract_bot_b_bots_summary(bot_b)

    data_items = _dedupe(bot_b_summary)
    if groups or quote_users:
        data_items.append(f"Gruppi: {', '.join(_dedupe(groups + quote_users))}")

    history = _dedupe(_extract_bot_a_history(bot_a) + groups + quote_users)
    dati = ' | '.join(data_items) if data_items else 'N/D'

    lines = [
        '✅ Tipo risultato: Aggregato Test1',
        f'👤 Identificatore: {target}',
        f'🆔 ID: {final_id}',
        f'🗓️ Registrazione: {_clean_visible(final_registration)}',
        f'📞 Telefono: {_clean_visible(final_phone)}',
        f'📊 Dati: {_clean_visible(dati)}',
    ]

    if raw.bot_a_retry_after:
        lines.append(f'⏳ Bot A temporaneamente occupato. Riprova tra {raw.bot_a_retry_after}')
    elif raw.bot_a_wait_until:
        lines.append(f'⚠️ Bot A non disponibile fino alle {raw.bot_a_wait_until}')

    lines.append('🕒 Storico:')
    lines.extend([f'• {item}' for item in history] or ['• Nessun dato disponibile'])
    lines.append(f'\n⏱️ Tempo elaborazione: {elapsed_ms} ms')

    status = '+' if any(x != 'N/D' for x in (final_id, final_phone, final_registration)) else '-'
    if raw.bot_a_retry_after or raw.bot_a_wait_until:
        status = '!' if status == '-' else status

    return SearchResult(
        target=target,
        lines=[_clean_visible(line) for line in lines],
        elapsed_ms=elapsed_ms,
        status=status,
        bot_a_seconds=raw.bot_a_seconds,
        bot_b_seconds=raw.bot_b_seconds,
    )
