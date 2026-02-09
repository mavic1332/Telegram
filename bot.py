import asyncio
import contextlib
from typing import Dict

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from pipeline import SearchPipeline
from utils import is_valid_target


def _result_keyboard(target: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='🤖 Riprova Bot A', callback_data=f'retry_a:{target}')],
            [InlineKeyboardButton(text='📡 Approfondisci Bot B', callback_data=f'retry_b:{target}')],
            [
                InlineKeyboardButton(text='⚙️ Impostazioni', callback_data='settings'),
                InlineKeyboardButton(text='🗑️ Reset', callback_data='reset'),
            ],
        ]
    )


async def _run_with_progress(message: Message, pipeline: SearchPipeline, target: str, mode: str) -> None:
    progress = await message.answer('Elaborazione in corso... 0%')

    async def animate() -> None:
        for percent in (10, 25, 50, 75, 90):
            await asyncio.sleep(0.5)
            await progress.edit_text(f'Elaborazione in corso... {percent}%')

    animation_task = asyncio.create_task(animate())
    try:
        result = await pipeline.run(target, mode=mode)
    finally:
        animation_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await animation_task

    await progress.edit_text('Elaborazione in corso... 100%')
    await message.answer('\n'.join(result.lines), reply_markup=_result_keyboard(target))


def setup_handlers(dp: Dispatcher, pipeline: SearchPipeline) -> None:
    last_target_by_chat: Dict[int, str] = {}

    @dp.message(CommandStart())
    async def on_start(message: Message) -> None:
        await message.answer('Ciao! Inviami un @username o un ID per avviare la ricerca.')

    @dp.message(F.text)
    async def on_query(message: Message) -> None:
        target = (message.text or '').strip()
        if not is_valid_target(target):
            return
        last_target_by_chat[message.chat.id] = target
        await _run_with_progress(message, pipeline, target, mode='all')

    @dp.callback_query(F.data.startswith('retry_a:'))
    async def on_retry_a(callback: CallbackQuery) -> None:
        target = callback.data.split(':', 1)[1]
        await callback.answer('Riprovo Bot A...')
        await _run_with_progress(callback.message, pipeline, target, mode='bot_a')

    @dp.callback_query(F.data.startswith('retry_b:'))
    async def on_retry_b(callback: CallbackQuery) -> None:
        target = callback.data.split(':', 1)[1]
        await callback.answer('Approfondisco Bot B...')
        await _run_with_progress(callback.message, pipeline, target, mode='bot_b')

    @dp.callback_query(F.data == 'settings')
    async def on_settings(callback: CallbackQuery) -> None:
        await callback.answer()
        await callback.message.answer('⚙️ Impostazioni: modifica il file .env e riavvia il bot.')

    @dp.callback_query(F.data == 'reset')
    async def on_reset(callback: CallbackQuery) -> None:
        await callback.answer('Reset eseguito')
        last_target_by_chat.pop(callback.message.chat.id, None)
        await callback.message.answer('🗑️ Stato ricerca azzerato. Invia un nuovo @username o ID.')


async def run_frontend(bot_token: str, pipeline: SearchPipeline) -> None:
    bot = Bot(token=bot_token)
    dp = Dispatcher()
    setup_handlers(dp, pipeline)
    await dp.start_polling(bot)
