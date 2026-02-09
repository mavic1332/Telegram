from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.models import ServiceAResult


class ServiceAClient:
    async def lookup(self, canonical_id: str, normalized_identifier: str, search_type: str) -> ServiceAResult:
        if settings.service_a_base_url == "mock":
            return ServiceAResult(
                id=canonical_id,
                phone=normalized_identifier if not normalized_identifier.startswith("@") else "+39000111222",
                display_name="Mario Rossi",
                tags=["cliente", search_type.lower()],
                history=["2024-10-10 -> registrazione", "2025-01-11 -> chiamata uscente"],
                counters={"calls": 12, "tickets": 1},
                extra={"segment": "gold"},
                updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )

        headers = {"Authorization": f"Bearer {settings.service_a_api_key}"}
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
                    resp = await client.post(f"{settings.service_a_base_url}/lookup", headers=headers, json=payload)
                    resp.raise_for_status()
                    return ServiceAResult.model_validate(resp.json())
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise RuntimeError("Lookup failed") from last_error
