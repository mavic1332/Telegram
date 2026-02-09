import asyncio

from bot import run_frontend
from config import load_settings
from pipeline import SearchPipeline
from resolver_client import ResolverClient


async def main() -> None:
    settings = load_settings()
    resolver = ResolverClient(
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        phone=settings.phone,
    )

    await resolver.start()
    pipeline = SearchPipeline(resolver)

    try:
        await run_frontend(settings.bot_token, pipeline)
    finally:
        await resolver.stop()


if __name__ == '__main__':
    asyncio.run(main())
