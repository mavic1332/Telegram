import asyncio
from typing import Awaitable, Callable, Optional

from merge import build_report
from models import RawBotResponses, SearchResult
from resolver_client import ResolverClient
from utils import now_ms

PIPELINE_BOT_TIMEOUT_S = 180
ProgressCb = Optional[Callable[[str], Awaitable[None]]]


class SearchPipeline:
    def __init__(self, resolver: ResolverClient) -> None:
        self.resolver = resolver

    async def run(self, target: str, mode: str = 'all', progress_cb: ProgressCb = None) -> SearchResult:
        normalized_mode = mode if mode in {'all', 'bot_a', 'bot_b'} else 'all'
        started = now_ms()
        try:
            raw = await asyncio.wait_for(
                self.resolver.fetch_info(target, mode=normalized_mode, progress_cb=progress_cb),
                timeout=PIPELINE_BOT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            raw = RawBotResponses(botfindinformation='Timeout su Bot A.', wow_myai='Timeout su Bot B.')
        elapsed = max(1, now_ms() - started)
        result = build_report(raw, elapsed_ms=elapsed, target=target)
        if progress_cb:
            await progress_cb('parsed')
        return result
