import re
from typing import Dict, Iterable, List

from models import SearchResult

SOURCE_PATTERNS = [
    r'@Botfindinformation_bot',
    r'@WOW_MYAI_BOT',
    r'(?im)^.*powered\s+by.*$',
    r'(?im)^.*join\s+channel.*$',
    r'https?://t\.me/\S+',
]


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
        line = raw.strip('•- \t')
        if not line:
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


def build_report(raw: Dict[str, str], elapsed_ms: int, target: str) -> SearchResult:
    merged = _sanitize('\n'.join(raw.values()))
    lines = _dedupe(merged.splitlines())

    summary = [
        '✅ Tipo risultato: Aggregato Test1',
        f'👤 Identificatore: {target}',
        f'🆔 ID: {_pick(lines, " id", "id:")}',
        f'🗓️ Registrazione: {_pick(lines, "registr", "created")}',
        f'👱 Nome: {_pick(lines, "nome", "name")}',
        f'📞 Telefono: {_pick(lines, "phone", "telefono")}',
        f'📊 Dati: {_pick(lines, "call", "ticket", "payment", "pagament")}',
        '🕒 Storico:',
    ]
    history = [f'• {line}' for line in lines[:12]] or ['• Nessun dato disponibile']

    report_lines = summary + history + [f'\n⏱️ Tempo elaborazione: {elapsed_ms} ms']
    return SearchResult(target=target, lines=report_lines, elapsed_ms=elapsed_ms)
