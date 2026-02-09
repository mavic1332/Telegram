# test1 Telegram Bot + Local Gateway

Progetto completo con:
- **bot Telegram async** (Python 3.11+) chiamato `test1`
- **gateway locale FastAPI** (`gateway/`) con endpoint:
  - `POST /telegram/resolve`
  - `POST /telegram/enrich`

Il bot mantiene output utente neutrale (nessun nome di fonti/servizi).

## Architettura
1. Utente invia telefono o `@username` al bot.
2. Bot chiama gateway `/telegram/resolve` per ottenere `canonical_id`.
3. Bot chiama gateway `/telegram/enrich` e applica merge finale locale.
4. Bot mostra una sola scheda unificata.

## Modalità gateway
### 1) MOCK (default)
Se `GATEWAY_DB_PATH` è vuoto, il gateway restituisce dati finti realistici e **deterministici** in base alla query.

### 2) DB MODE
Se `GATEWAY_DB_PATH` è impostato, il gateway legge SQLite:
- tabella `contacts`
- tabella `history`

## Sicurezza gateway
Header `X-API-KEY` obbligatorio su tutti gli endpoint.

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Configura `.env` con almeno:
```env
TELEGRAM_BOT_TOKEN=<token_bot>
VOIP_BASE_URL=http://127.0.0.1:8000
VOIP_API_KEY=change-me
GATEWAY_API_KEY=change-me
GATEWAY_DB_PATH=
```

## Avvio gateway
```bash
python -m gateway.main
```

## Avvio bot
```bash
python -m app.main
```

## Esempi curl gateway
### Resolve
```bash
curl -X POST 'http://127.0.0.1:8000/telegram/resolve' \
  -H 'Content-Type: application/json' \
  -H 'X-API-KEY: change-me' \
  -d '{"identifier":"@ciao1234","search_type":"Telegram"}'
```

### Enrich
```bash
curl -X POST 'http://127.0.0.1:8000/telegram/enrich' \
  -H 'Content-Type: application/json' \
  -H 'X-API-KEY: change-me' \
  -d '{"canonical_id":"CID-ABC123","normalized_identifier":"@ciao1234","search_type":"Telegram"}'
```

## Avvio test
```bash
pytest -q
```

## Note sicurezza/operatività bot
- allowlist chat con `ALLOWED_CHAT_IDS`
- rate limit per chat (1 richiesta ogni 3 secondi)
- masking nei log
- audit SQLite minimale (senza identificatori in chiaro)
