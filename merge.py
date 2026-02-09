import re
from typing import List, Optional

from models import RawBotResponses, SearchResult

CYRILLIC_WORD_RE = re.compile(r'[а-яА-Я]+')
MONTH_IT = {
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


def _translate_registered(value: str) -> str:
    text = value.strip(' []')
    for en, it in MONTH_IT.items():
        text = re.sub(rf'\b{en}\b', it, text, flags=re.IGNORECASE)
    return text


def _extract_bot_b(raw_b: str) -> tuple[Optional[str], Optional[str], List[str]]:
    text = _strip_noise(raw_b)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    found_id: Optional[str] = None
    registered: Optional[str] = None
    history: List[str] = []

    for i, line in enumerate(lines):
        lower = line.lower()

        if 'search by telegram id' in lower and not found_id:
            match = re.search(r'(\d{7,10})\D*$', line)
            if match:
                found_id = match.group(1)
            continue

        if 'registered' in lower and not registered:
            inline = line.split('Registered', 1)[1].strip(' :[]') if 'Registered' in line else ''
            if inline:
                registered = _translate_registered(inline)
            elif i + 1 < len(lines):
                registered = _translate_registered(lines[i + 1])
            continue

        history.append(line)

    return found_id, registered, history


def _section_between(text: str, start_anchor: str, stop_anchors: tuple[str, ...]) -> List[str]:
    start = text.find(start_anchor)
    if start == -1:
        return []
    chunk = text[start + len(start_anchor):]
    stop_idx = len(chunk)
    for stop in stop_anchors:
        idx = chunk.find(stop)
        if idx != -1:
            stop_idx = min(stop_idx, idx)
    body = chunk[:stop_idx]
    return [ln.strip('•- \t') for ln in body.splitlines() if ln.strip()]


def _extract_bot_a(raw_a: str) -> tuple[Optional[str], Optional[str], Optional[str], List[str], List[str]]:
    text = _strip_noise(raw_a)

    id_match = re.search(r'💬\s*ID\s*:\s*(\d+)', text)
    phone_match = re.search(r'📞\s*Телефон\s*:\s*([^\n\r]+)', text)
    links_match = re.search(r'📖\s*Контактные\s*связи\s*:\s*([^\n\r]+)', text)

    id_val = id_match.group(1).strip() if id_match else None
    phone_val = phone_match.group(1).strip() if phone_match else None
    links_val = links_match.group(1).strip() if links_match else None

    history = _section_between(text, '🕓 История изменения имени', ('👥 Группы', '📖 Контактные связи', '📞 Телефон'))
    groups = _section_between(text, '👥 Группы', ('🕓 История изменения имени', '📖 Контактные связи', '📞 Телефон'))
    groups = [g for g in groups if g.startswith('@') or 'http' not in g.lower()]

    return id_val, phone_val, links_val, history, groups


def _clean_final(line: str) -> str:
    no_cyr = CYRILLIC_WORD_RE.sub('', line)
    no_cyr = re.sub(r'\s{2,}', ' ', no_cyr).strip(' :-')
    return no_cyr.strip()


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        v = _clean_final(value)
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def build_report(raw: RawBotResponses, elapsed_ms: int, target: str) -> SearchResult:
    id_a, phone_a, links_a, history_a, groups_a = _extract_bot_a(raw.botfindinformation)
    id_b, reg_b, history_b = _extract_bot_b(raw.wow_myai)

    merged_history = _dedupe(history_a + groups_a + history_b)
    dati = _dedupe([links_a] if links_a else [])
    if groups_a:
        dati.extend(_dedupe([f'Gruppi: {", ".join(groups_a)}']))

    final_id = id_a or id_b or 'N/D'
    final_reg = _clean_final(reg_b) if reg_b else 'N/D'
    final_phone = _clean_final(phone_a) if phone_a else 'N/D'

    summary = [
        '✅ Tipo risultato: Aggregato Test1',
        f'👤 Identificatore: {target}',
        f'🆔 ID: {final_id}',
        f'🗓️ Registrazione: {final_reg}',
        f'📞 Telefono: {final_phone}',
        f'📊 Dati: {" | ".join(dati) if dati else "N/D"}',
    ]

    if raw.bot_a_retry_after:
        summary.append(f'⏳ Bot A temporaneamente occupato. Riprova tra {raw.bot_a_retry_after}')
    elif raw.bot_a_wait_until:
        summary.append(f'⚠️ Bot A non disponibile fino alle {raw.bot_a_wait_until}')

    storico = _dedupe(merged_history)[:12]
    summary.append('🕒 Storico:')
    summary.extend([f'• {s}' for s in storico] or ['• Nessun dato disponibile'])
    summary.append(f'\n⏱️ Tempo elaborazione: {elapsed_ms} ms')

    status = '!'
    if final_id != 'N/D' or final_phone != 'N/D' or storico:
        status = '+'
    elif raw.bot_a_retry_after or raw.bot_a_wait_until:
        status = '!'
    else:
        status = '-'

    return SearchResult(
        target=target,
        lines=[_clean_final(line) for line in summary],
        elapsed_ms=elapsed_ms,
        status=status,
        bot_a_seconds=raw.bot_a_seconds,
        bot_b_seconds=raw.bot_b_seconds,
    )
