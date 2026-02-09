import asyncio
import contextlib

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from pipeline import SearchPipeline
from utils import is_valid_target


def _result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='🔁 Nuova ricerca', callback_data='new_search')],
            [InlineKeyboardButton(text='💬 Apri dialogo', url='https://t.me/Test1')],
        ]
    )


def setup_handlers(dp: Dispatcher, pipeline: SearchPipeline) -> None:
    @dp.message(CommandStart())
    async def on_start(message: Message) -> None:
        await message.answer('Ciao! Inviami un @username o un ID per avviare la ricerca.')

    @dp.message(F.text)
    async def on_query(message: Message) -> None:
        target = (message.text or '').strip()
        if not is_valid_target(target):
            return

        progress = await message.answer('Elaborazione in corso... 0%')

        async def animate() -> None:
            for percent in (10, 25, 50, 75, 90):
                await asyncio.sleep(0.5)
                await progress.edit_text(f'Elaborazione in corso... {percent}%')

        animation_task = asyncio.create_task(animate())
        try:
            result = await pipeline.run(target)
        finally:
            animation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await animation_task

        await progress.edit_text('Elaborazione in corso... 100%')
        await message.answer('\n'.join(result.lines), reply_markup=_result_keyboard())


async def run_frontend(bot_token: str, pipeline: SearchPipeline) -> None:
    bot = Bot(token=bot_token)
    dp = Dispatcher()
    setup_handlers(dp, pipeline)
    await dp.start_polling(bot)
