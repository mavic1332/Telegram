# test1 Telegram Bot

Bot Telegram async (Python 3.11+) con pipeline in 2 fasi:
1. **Resolver primario**: da telefono/@username produce `canonical_id` + metadati minimi.
2. **Arricchimento + merge**: interroga due servizi interni in parallelo e restituisce una scheda unificata.

> L'output utente non espone mai nomi di servizi/fonti/endpoint.

## Requisiti
- Python 3.11+
- Dipendenze in `requirements.txt`

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Compila `.env`:
```env
TELEGRAM_BOT_TOKEN=
RESOLVER_BASE_URL=mock
RESOLVER_API_KEY=
SERVICE_A_BASE_URL=mock
SERVICE_A_API_KEY=
SERVICE_B_BASE_URL=mock
SERVICE_B_API_KEY=
VOIP_TIMEOUT_SECONDS=10
ALLOWED_CHAT_IDS=123,456
AUDIT_DB_PATH=./audit.db
LOG_LEVEL=INFO
MASK_OUTPUT=false
```

## Avvio
```bash
python -m app.main
```

## Flow conversazionale
- `/start` mostra prompt iniziale.
- Input utente:
  - `@username` valido: `^@[A-Za-z0-9_]{5,32}$`
  - altrimenti telefono (normalizzato)
- Mostra keyboard con tipo ricerca (`Telegram`, `Instagram`, `Tiktok`).
- Callback:
  - messaggio iniziale `⏳ Sto cercando, attendi…`
  - progress update: `Search… 25%`, `Search… 75%`
  - fase 1 resolver (timeout+retry)
  - fase 2 enrichment in parallelo (timeout+retry, degradazione elegante)
  - output unico finale

## Sicurezza
- **Allowlist chat_id** con `ALLOWED_CHAT_IDS`.
- **Rate-limit**: 1 richiesta / 3 secondi per chat.
- **Logging con masking**: identifier mai in chiaro nei log error.
- **Audit SQLite**: salva solo timestamp/chat_id/search_type/esito/durata.

## Mock mode
Se `RESOLVER_BASE_URL`, `SERVICE_A_BASE_URL`, `SERVICE_B_BASE_URL` sono `mock`, il bot restituisce dati realistici fittizi utili per sviluppo locale.

## Test
```bash
pytest -q
```

Copertura minima inclusa:
- validazione input
- merge
- pipeline mock
- masking
- rate limit
