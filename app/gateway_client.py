from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel

from app.config import settings
from app.models import ServiceAResult, ServiceBResult


class EnrichResponseModel(BaseModel):
    service_a: ServiceAResult
    service_b: ServiceBResult


class GatewayClient:
    async def enrich(self, canonical_id: str, normalized_identifier: str, search_type: str) -> tuple[ServiceAResult, ServiceBResult]:
        if settings.voip_base_url == "mock":
            return (
                ServiceAResult(
                    id=canonical_id,
                    phone=normalized_identifier if not normalized_identifier.startswith("@") else "+39000111222",
                    display_name="Mario Rossi",
                    tags=["cliente", search_type.lower()],
                    history=["2024-10-10 -> registrazione", "2025-01-11 -> chiamata uscente"],
                    counters={"calls": 12, "tickets": 1},
                    extra={"segment": "gold"},
                    updated_at=datetime.now(UTC) - timedelta(hours=1),
                ),
                ServiceBResult(
                    id=canonical_id,
                    phone="+39000999888",
                    display_name="M. Rossi",
                    tags=["voip", "attivo"],
                    history=["2025-01-11 -> chiamata uscente", "2025-01-12 -> pagamento"],
                    counters={"calls": 14, "payments": 3},
                    extra={"language": "it"},
                    updated_at=datetime.now(UTC),
                ),
            )

        payload = {
            "canonical_id": canonical_id,
            "normalized_identifier": normalized_identifier,
            "search_type": search_type,
        }
        headers = {"X-API-KEY": settings.voip_api_key}
        timeout = settings.voip_timeout_seconds
        last_error: Exception | None = None
        for _ in range(2):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(f"{settings.voip_base_url}/telegram/enrich", json=payload, headers=headers)
                    resp.raise_for_status()
                    data = EnrichResponseModel.model_validate(resp.json())
                    return data.service_a, data.service_b
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise RuntimeError("Enrichment failed") from last_error
