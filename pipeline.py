from merge import build_report
from models import SearchResult
from resolver_client import ResolverClient
from utils import now_ms


class SearchPipeline:
    def __init__(self, resolver: ResolverClient) -> None:
        self.resolver = resolver

    async def run(self, target: str, mode: str = 'all') -> SearchResult:
        started = now_ms()
        raw = await self.resolver.fetch_info(target, mode=mode)
        elapsed = max(1, now_ms() - started)
        return build_report(raw, elapsed_ms=elapsed, target=target)
