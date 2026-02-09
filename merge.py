import re
from typing import Dict, Iterable, List

from models import RawBotResponses, SearchResult

SOURCE_PATTERNS = [
    r'@Botfindinformation_bot',
    r'@WOW_MYAI_BOT',
    r'@UniversalSearch',
    r'fake\s+generator\s+bot',
    r'(?im)^\s*by\s+.*$',
    r'(?im)^.*powered\s+by.*$',
    r'(?im)^.*join\s+channel.*$',
    r'https?://t\.me/\S+',
]
CYRILLIC_RE = re.compile(r'[\u0400-\u04FF]')
MONTH_MAP = {
    'january': '01', 'february': '02', 'march': '03', 'april': '04', 'may': '05', 'june': '06',
    'july': '07', 'august': '08', 'september': '09', 'october': '10', 'november': '11', 'december': '12',
}


def _translate_status(line: str) -> str:
    lowered = line.lower()
    if any(x in lowered for x in ('not found', 'не найден', 'не найдено', 'нет данных')):
        return 'Nessun dato trovato'
    if any(x in lowered for x in ('limit reached', 'лимит', 'достигнут лимит')):
        return 'Limite raggiunto'
    return line


def _normalize_registration(line: str) -> str:
    match = re.search(r'registered\s*:\s*([A-Za-z]+)\s+(\d{4})', line, flags=re.IGNORECASE)
    if not match:
        return line
    month = MONTH_MAP.get(match.group(1).lower())
    if not month:
        return line
    return f'Registrazione: {month}/{match.group(2)}'


def _sanitize(text: str) -> str:
    cleaned = text
    for pattern in SOURCE_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def _dedupe(lines: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for raw in lines:
        line = _translate_status(_normalize_registration(raw.strip('•- \t')))
        if not line or CYRILLIC_RE.search(line):
            continue
        key = re.sub(r'\s+', ' ', line).lower().strip()
        if key in seen:
            continue
        seen.add(key)
        output.append(line)
    return output


def _pick(lines: List[str], *keys: str) -> str:
    for line in lines:
        lower = line.lower()
        if any(k in lower for k in keys):
            return line
    return 'N/D'


def build_report(raw: RawBotResponses, elapsed_ms: int, target: str) -> SearchResult:
    merged = _sanitize('\n'.join(raw.as_dict().values()))
    lines = _dedupe(merged.splitlines())

    summary = [
        '✅ Tipo risultato: Aggregato Test1',
        f'👤 Identificatore: {target}',
        f'🆔 ID: {_pick(lines, " id", "id:")}',
        f'🗓️ Registrazione: {_pick(lines, "registr")}',
        f'👱 Nome: {_pick(lines, "nome", "name")}',
        f'📞 Telefono: {_pick(lines, "phone", "telefono")}',
        f'📊 Dati: {_pick(lines, "call", "ticket", "payment", "pagament")}',
    ]

    if raw.bot_a_wait_until:
        summary.append(f'⚠️ Bot A non disponibile fino alle {raw.bot_a_wait_until}')

    summary.append('🕒 Storico:')
    history = [f'• {line}' for line in lines[:12]] or ['• Nessun dato disponibile']

    report_lines = summary + history + [f'\n⏱️ Tempo elaborazione: {elapsed_ms} ms']
    return SearchResult(target=target, lines=report_lines, elapsed_ms=elapsed_ms)
