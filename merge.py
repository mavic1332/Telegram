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
    return match.group(1) if match else None


def _extract_bot_b_registered(text: str) -> Optional[str]:
    match = re.search(r'(?is)Registered\s*\n\s*(.*?)(?:\n\s*🤖\s*Bots\b|$)', text)
    if not match:
        return None
    block = match.group(1)
    lines = [ln.strip() for ln in re.split(r'\r?\n', block) if ln.strip()]
    if not lines:
        return None
    return _to_it_month(', '.join(lines))


def _extract_bot_a_phone(text: str) -> Optional[str]:
    match = re.search(r'(?is)(?:Телефон\s*:|📞\s*)(\d{10,})', text)
    return match.group(1) if match else None


def _extract_bot_a_id(text: str) -> Optional[str]:
    match = re.search(r'(?im)\bID\s*:\s*(\d+)', text)
    return match.group(1) if match else None


def _extract_bot_a_history(text: str) -> list[str]:
    match = re.search(r'(?is)История\s+изменения\s+имени\s*:\s*(.*?)\s*👥\s*Группы\s*:', text)
    if not match:
        return []
    block = match.group(1)
    return [ln.strip('•- \t') for ln in re.split(r'\r?\n', block) if ln.strip()]


def _extract_bot_a_groups(text: str) -> list[str]:
    match = re.search(r'(?is)👥\s*Группы\s*:\s*(.*?)(?:\n\s*(?:📖|🕓|📞|$))', text)
    if not match:
        return []
    return re.findall(r'@[A-Za-z0-9_]{3,}', match.group(1))


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

    history = _dedupe(_extract_bot_a_history(bot_a) + _extract_bot_a_groups(bot_a))
    dati = f"Gruppi: {', '.join(_extract_bot_a_groups(bot_a))}" if _extract_bot_a_groups(bot_a) else 'N/D'

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
