from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models import ResolverResult


class ResolverClient:
    async def resolve(self, identifier: str, search_type: str) -> ResolverResult:
        if settings.resolver_base_url == "mock":
            return ResolverResult(
                canonical_id=f"CID-{identifier.replace('@', '').replace('+', '')[:12]}",
                created_at=datetime.now(timezone.utc),
                normalized_identifier=identifier,
                notes_min=f"Resolver ok ({search_type})",
            )

        payload = {"identifier": identifier, "search_type": search_type}
        headers = {"Authorization": f"Bearer {settings.resolver_api_key}"}
        timeout = settings.voip_timeout_seconds
        last_error: Exception | None = None
        for _ in range(2):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(f"{settings.resolver_base_url}/resolve", json=payload, headers=headers)
                    resp.raise_for_status()
                    return ResolverResult.model_validate(resp.json())
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise RuntimeError("Resolver failed") from last_error
