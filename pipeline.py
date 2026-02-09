import asyncio

from merge import build_report
from models import RawBotResponses, SearchResult
from resolver_client import ResolverClient
from utils import now_ms

PIPELINE_BOT_TIMEOUT_S = 180


class SearchPipeline:
    def __init__(self, resolver: ResolverClient) -> None:
        self.resolver = resolver

    async def run(self, target: str, mode: str = 'all') -> SearchResult:
        normalized_mode = mode if mode in {'all', 'bot_a', 'bot_b'} else 'all'
        started = now_ms()
        try:
            raw = await asyncio.wait_for(
                self.resolver.fetch_info(target, mode=normalized_mode),
                timeout=PIPELINE_BOT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            raw = RawBotResponses(
                botfindinformation='Timeout su Bot A.',
                wow_myai='Timeout su Bot B.',
            )
        elapsed = max(1, now_ms() - started)
        return build_report(raw, elapsed_ms=elapsed, target=target)
