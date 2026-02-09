from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models import ServiceBResult


class ServiceBClient:
    async def lookup(self, canonical_id: str, normalized_identifier: str, search_type: str) -> ServiceBResult:
        if settings.service_b_base_url == "mock":
            return ServiceBResult(
                id=canonical_id,
                phone="+39000999888",
                display_name="M. Rossi",
                tags=["voip", "attivo"],
                history=["2025-01-11 -> chiamata uscente", "2025-01-12 -> pagamento"],
                counters={"calls": 14, "payments": 3},
                extra={"language": "it"},
                updated_at=datetime.now(timezone.utc),
            )

        headers = {"Authorization": f"Bearer {settings.service_b_api_key}"}
        payload = {
            "canonical_id": canonical_id,
            "normalized_identifier": normalized_identifier,
            "search_type": search_type,
        }
        timeout = settings.voip_timeout_seconds
        last_error: Exception | None = None
        for _ in range(2):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(f"{settings.service_b_base_url}/lookup", headers=headers, json=payload)
                    resp.raise_for_status()
                    return ServiceBResult.model_validate(resp.json())
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise RuntimeError("Lookup failed") from last_error
