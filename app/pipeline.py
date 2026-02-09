from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from app.gateway_client import GatewayClient
from app.merge import merge_results
from app.models import UnifiedResult
from app.resolver_client import ResolverClient

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self) -> None:
        self.resolver = ResolverClient()
        self.gateway = GatewayClient()

    async def run(
        self,
        normalized_identifier: str,
        search_type: str,
        progress_cb: Callable[[str], Awaitable[None]],
    ) -> UnifiedResult:
        await progress_cb("Search… 25%")
        start = time.monotonic()
        resolver_task = asyncio.create_task(self.resolver.resolve(normalized_identifier, search_type))
        await asyncio.sleep(0.4)
        await progress_cb("Search… 75%")
        resolver_result = await resolver_task

        a_result = None
        b_result = None
        try:
            a_result, b_result = await self.gateway.enrich(
                resolver_result.canonical_id,
                normalized_identifier,
                search_type,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Enrichment unavailable for canonical_id=%s", resolver_result.canonical_id)

        unified = merge_results(search_type, resolver_result, a_result, b_result)
        unified.notes = unified.notes or f"Elaborazione completata in {int((time.monotonic()-start)*1000)} ms"
        return unified
