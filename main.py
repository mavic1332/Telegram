import asyncio

from bot import run_bot
from config import load_settings
from resolver_client import ResolverClient


async def runner() -> None:
    settings = load_settings()
    resolver = ResolverClient(
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        phone_number=settings.phone_number,
    )

    await resolver.start()
    shutdown_waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    try:
        await run_bot(settings.bot_token, resolver, shutdown_waiter)
    finally:
        if not shutdown_waiter.done():
            shutdown_waiter.set_result(None)
        await resolver.stop()


if __name__ == '__main__':
    asyncio.run(runner())
