from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from app.merge import merge_results
from app.models import UnifiedResult
from app.resolver_client import ResolverClient
from app.services.service_a import ServiceAClient
from app.services.service_b import ServiceBClient

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self) -> None:
        self.resolver = ResolverClient()
        self.service_a = ServiceAClient()
        self.service_b = ServiceBClient()

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

        results = await asyncio.gather(
            self.service_a.lookup(resolver_result.canonical_id, normalized_identifier, search_type),
            self.service_b.lookup(resolver_result.canonical_id, normalized_identifier, search_type),
            return_exceptions=True,
        )

        a_result = None if isinstance(results[0], Exception) else results[0]
        b_result = None if isinstance(results[1], Exception) else results[1]

        if not a_result and not b_result:
            logger.warning("Enrichment unavailable for canonical_id=%s", resolver_result.canonical_id)

        unified = merge_results(search_type, resolver_result, a_result, b_result)
        unified.notes = unified.notes or f"Elaborazione completata in {int((time.monotonic()-start)*1000)} ms"
        return unified
