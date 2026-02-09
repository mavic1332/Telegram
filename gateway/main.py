from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Local VoIP Gateway", version="1.0.0")


class ResolveRequest(BaseModel):
    identifier: str
    search_type: str


class ResolveResponse(BaseModel):
    canonical_id: str
    created_at: Optional[datetime] = None
    normalized_identifier: str
    notes_min: Optional[str] = None


class ServicePayload(BaseModel):
    id: Optional[str] = None
    phone: Optional[str] = None
    display_name: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)
    counters: dict[str, int] = Field(default_factory=dict)
    extra: dict[str, str] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class EnrichRequest(BaseModel):
    canonical_id: str
    normalized_identifier: str
    search_type: str


class EnrichResponse(BaseModel):
    service_a: ServicePayload
    service_b: ServicePayload


def _api_key_required(x_api_key: str | None) -> None:
    expected = os.getenv("GATEWAY_API_KEY", "change-me")
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _normalize_phone(value: str) -> str:
    cleaned = re.sub(r"[\s\-()]+", "", value)
    if cleaned.startswith("+"):
        return "+" + re.sub(r"\D", "", cleaned[1:])
    return re.sub(r"\D", "", cleaned)


def _deterministic_seed(*parts: str) -> int:
    material = "|".join(parts).encode("utf-8")
    return int(hashlib.sha256(material).hexdigest()[:8], 16)


def _mock_resolve(req: ResolveRequest) -> ResolveResponse:
    ident = req.identifier if req.identifier.startswith("@") else _normalize_phone(req.identifier)
    seed = _deterministic_seed(ident, req.search_type)
    created = datetime(2022, 1, 1, tzinfo=UTC) + timedelta(days=seed % 800)
    cid = f"CID-{hashlib.sha1(ident.encode()).hexdigest()[:10].upper()}"
    return ResolveResponse(
        canonical_id=cid,
        created_at=created,
        normalized_identifier=ident,
        notes_min="ok",
    )


def _mock_enrich(req: EnrichRequest) -> EnrichResponse:
    seed = _deterministic_seed(req.canonical_id, req.normalized_identifier, req.search_type)
    base_phone = req.normalized_identifier if req.normalized_identifier.startswith("+") else f"+39{seed % 900000000 + 100000000}"
    ts = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=seed % 30)
    return EnrichResponse(
        service_a=ServicePayload(
            id=req.canonical_id,
            phone=base_phone,
            display_name=f"Utente {seed % 100}",
            tags=["cliente", req.search_type.lower()],
            history=["2025-01-10 -> registrazione", "2025-01-12 -> chiamata uscente"],
            counters={"calls": (seed % 25) + 3, "tickets": seed % 4},
            extra={"segment": "gold" if seed % 2 == 0 else "silver"},
            updated_at=ts,
        ),
        service_b=ServicePayload(
            id=req.canonical_id,
            phone=f"+39{(seed + 3333) % 900000000 + 100000000}",
            display_name=f"U. {seed % 100}",
            tags=["voip", "attivo"],
            history=["2025-01-12 -> chiamata uscente", "2025-01-13 -> pagamento"],
            counters={"calls": (seed % 30) + 1, "payments": seed % 6},
            extra={"language": "it"},
            updated_at=ts + timedelta(hours=2),
        ),
    )


def _connect_db() -> sqlite3.Connection:
    db_path = os.getenv("GATEWAY_DB_PATH", "").strip()
    if not db_path:
        raise RuntimeError("DB mode non abilitata")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _db_resolve(req: ResolveRequest) -> ResolveResponse:
    identifier = req.identifier.strip()
    is_username = identifier.startswith("@")
    normalized = identifier if is_username else _normalize_phone(identifier)
    with _connect_db() as conn:
        if is_username:
            row = conn.execute(
                "SELECT canonical_id, username, created_at FROM contacts WHERE username = ? LIMIT 1",
                (normalized,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT canonical_id, phone, created_at FROM contacts WHERE phone = ? LIMIT 1",
                (normalized,),
            ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Identifier not found")
    created_at = datetime.fromisoformat(row["created_at"]) if row["created_at"] else None
    return ResolveResponse(
        canonical_id=row["canonical_id"],
        created_at=created_at,
        normalized_identifier=normalized,
        notes_min="db",
    )


def _loads_or_empty(value: Any, default: Any) -> Any:
    if not value:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _db_enrich(req: EnrichRequest) -> EnrichResponse:
    with _connect_db() as conn:
        rows = conn.execute(
            """
            SELECT canonical_id, phone, display_name, tags, counters, extra, updated_at, source
            FROM contacts
            WHERE canonical_id = ? OR phone = ? OR username = ?
            """,
            (req.canonical_id, req.normalized_identifier, req.normalized_identifier),
        ).fetchall()
        hist_rows = conn.execute(
            "SELECT event_ts, event FROM history WHERE canonical_id = ? ORDER BY event_ts ASC",
            (req.canonical_id,),
        ).fetchall()

    history = [f"{r['event_ts']} -> {r['event']}" for r in hist_rows]

    def pick(source_name: str) -> ServicePayload:
        source_rows = [r for r in rows if (r["source"] or "").lower() == source_name]
        row = source_rows[0] if source_rows else (rows[0] if rows else None)
        if not row:
            return ServicePayload(id=req.canonical_id, history=history)
        return ServicePayload(
            id=row["canonical_id"],
            phone=row["phone"],
            display_name=row["display_name"],
            tags=_loads_or_empty(row["tags"], []),
            history=history,
            counters=_loads_or_empty(row["counters"], {}),
            extra=_loads_or_empty(row["extra"], {}),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    return EnrichResponse(service_a=pick("a"), service_b=pick("b"))


@app.post("/telegram/resolve", response_model=ResolveResponse)
def telegram_resolve(payload: ResolveRequest, x_api_key: str | None = Header(default=None, alias="X-API-KEY")) -> ResolveResponse:
    _api_key_required(x_api_key)
    if os.getenv("GATEWAY_DB_PATH", "").strip():
        return _db_resolve(payload)
    return _mock_resolve(payload)


@app.post("/telegram/enrich", response_model=EnrichResponse)
def telegram_enrich(payload: EnrichRequest, x_api_key: str | None = Header(default=None, alias="X-API-KEY")) -> EnrichResponse:
    _api_key_required(x_api_key)
    if os.getenv("GATEWAY_DB_PATH", "").strip():
        return _db_enrich(payload)
    return _mock_enrich(payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("gateway.main:app", host="0.0.0.0", port=8000, reload=False)
