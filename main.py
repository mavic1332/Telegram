import asyncio

from bot import run_frontend
from config import load_settings
from database import SilentDatabase
from pipeline import SearchPipeline
from resolver_client import ResolverClient
from utils import configure_logging


async def main() -> None:
    configure_logging()
    settings = load_settings()
    resolver = ResolverClient(
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        phones=settings.userbot_phones,
        session_names=settings.userbot_sessions,
    )
    db = SilentDatabase()

    await resolver.start()
    pipeline = SearchPipeline(resolver)

    try:
        await run_frontend(settings.bot_token, pipeline, db, settings.admin_id)
    finally:
        await resolver.stop()


if __name__ == '__main__':
    asyncio.run(main())
