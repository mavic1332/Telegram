import asyncio
import contextlib
import re

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from merge import build_test1_output
from resolver_client import ResolverClient

VALID_TARGET_RE = re.compile(r'^(?:@[A-Za-z0-9_]{5,}|\d{5,})$')


def _is_valid_target(text: str) -> bool:
    return bool(VALID_TARGET_RE.fullmatch(text.strip()))


def setup_handlers(dp: Dispatcher, resolver: ResolverClient) -> None:
    @dp.message(CommandStart())
    async def on_start(message: Message) -> None:
        await message.answer('Ciao! Inviami un @username o un ID per avviare la ricerca.')

    @dp.message(F.text)
    async def on_target(message: Message) -> None:
        text = (message.text or '').strip()
        if not _is_valid_target(text):
            return

        progress_msg = await message.answer('⏳ Elaborazione in corso... 0%')

        async def update_progress() -> None:
            for pct in (25, 50, 75):
                await asyncio.sleep(0.6)
                await progress_msg.edit_text(f'⏳ Elaborazione in corso... {pct}%')

        progress_task = asyncio.create_task(update_progress())
        try:
            raw = await resolver.fetch_info(text)
            result = build_test1_output(raw)
        finally:
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task

        await progress_msg.edit_text('⏳ Elaborazione in corso... 100%')
        await message.answer(result, parse_mode='Markdown')


async def run_bot(bot_token: str, resolver: ResolverClient, shutdown_waiter: asyncio.Future[None]) -> None:
    bot = Bot(token=bot_token)
    dp = Dispatcher()
    setup_handlers(dp, resolver)

    polling = asyncio.create_task(dp.start_polling(bot))
    done, pending = await asyncio.wait({polling, shutdown_waiter}, return_when=asyncio.FIRST_COMPLETED)

    for task in pending:
        task.cancel()
    for task in done:
        if task is polling and task.exception():
            raise task.exception()
