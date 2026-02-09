from __future__ import annotations

import httpx

from app.config import settings
from app.models import ServiceBResult


class ServiceBClient:
    async def lookup(self, canonical_id: str, normalized_identifier: str, search_type: str) -> ServiceBResult:
        payload = {
            "canonical_id": canonical_id,
            "normalized_identifier": normalized_identifier,
            "search_type": search_type,
        }
        headers = {"X-API-KEY": settings.voip_api_key}
        async with httpx.AsyncClient(timeout=settings.voip_timeout_seconds) as client:
            resp = await client.post(f"{settings.voip_base_url}/telegram/enrich", json=payload, headers=headers)
            resp.raise_for_status()
            return ServiceBResult.model_validate(resp.json().get("service_b", {}))
