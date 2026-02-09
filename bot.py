import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import SilentDatabase
from pipeline import SearchPipeline
from utils import is_valid_target, now_iso, ts_hms


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


def _username(user: Message | CallbackQuery) -> str:
    u = user.from_user
    if not u:
        return 'unknown'
    return f'@{u.username}' if u.username else f'id:{u.id}'


def _full_name(message: Message | CallbackQuery) -> str:
    u = message.from_user
    if not u:
        return 'Unknown'
    return ' '.join(x for x in [u.first_name, u.last_name] if x) or 'Unknown'


def _perf_log(result_status: str, bot_a: float | None, bot_b: float | None, total_s: float) -> str:
    marker = '[+]' if result_status == '+' else '[-]' if result_status == '-' else '[!]'
    return f"{marker} [PERF] Bot A: {bot_a or 0:.2f}s | Bot B: {bot_b or 0:.2f}s | Total: {total_s:.2f}s"


async def _run_with_progress(
    message: Message,
    pipeline: SearchPipeline,
    target: str,
    mode: str,
    db: SilentDatabase,
) -> None:
    progress = await message.answer('Elaborazione... 0%')

    last_percent = 0

    async def progress_cb(stage: str) -> None:
        nonlocal last_percent
        stage_map = {
            'bot_a_clicked': (20, 'Interazione Bot A... 20%'),
            'bot_a': (50, 'Dati Bot A ricevuti... 50%'),
            'bot_b': (90, 'Dati Bot B ricevuti... 90%'),
            'parsed': (100, 'Completato 100%'),
        }
        data = stage_map.get(stage)
        if not data:
            return
        pct, msg = data
        if pct <= last_percent:
            return
        last_percent = pct
        await progress.edit_text(msg)

    started = asyncio.get_running_loop().time()
    result = await pipeline.run(target, mode=mode, progress_cb=progress_cb)
    total_s = asyncio.get_running_loop().time() - started

    if last_percent < 100:
        await progress_cb('parsed')
    await message.answer('\n'.join(result.lines), reply_markup=_result_keyboard(target))

    logging.info(f"[{ts_hms()}] [USER: {_username(message)}] searched for: [{target}]")
    if 'Riprova tra' in '\n'.join(result.lines):
        for line in result.lines:
            if 'Riprova tra' in line:
                retry = line.split('Riprova tra', 1)[1].strip()
                logging.info(f"[!] Bot A Rate Limit: {retry} remaining")
                break
    logging.info(_perf_log(result.status, result.bot_a_seconds, result.bot_b_seconds, total_s))

    db.insert_search_event(
        telegram_id=message.from_user.id if message.from_user else 0,
        target=target,
        mode=mode,
        status=result.status,
        bot_a_seconds=result.bot_a_seconds,
        bot_b_seconds=result.bot_b_seconds,
        total_seconds=total_s,
        created_at=now_iso(),
    )


def setup_handlers(dp: Dispatcher, pipeline: SearchPipeline, db: SilentDatabase, admin_id: int) -> None:
    @dp.message(CommandStart())
    async def on_start(message: Message) -> None:
        if message.from_user:
            db.upsert_user(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                full_name=_full_name(message),
                ts=now_iso(),
            )
        await message.answer('Ciao! Inviami un @username o un ID per avviare la ricerca.')

    @dp.message(Command('admin_stats'))
    async def on_admin_stats(message: Message) -> None:
        if not message.from_user or message.from_user.id != admin_id:
            return
        await message.answer(f'👮 Utenti totali registrati: {db.total_users()}')

    @dp.message(F.text)
    async def on_query(message: Message) -> None:
        if message.from_user:
            db.upsert_user(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                full_name=_full_name(message),
                ts=now_iso(),
            )

        target = (message.text or '').strip()
        if not is_valid_target(target):
            return

        await _run_with_progress(message, pipeline, target, mode='all', db=db)

    @dp.callback_query(F.data.startswith('retry_a:'))
    async def on_retry_a(callback: CallbackQuery) -> None:
        target = callback.data.split(':', 1)[1]
        if callback.from_user:
            db.upsert_user(
                telegram_id=callback.from_user.id,
                username=callback.from_user.username,
                full_name=_full_name(callback),
                ts=now_iso(),
            )
        await callback.answer('Riprovo Bot A...')
        await _run_with_progress(callback.message, pipeline, target, mode='bot_a', db=db)

    @dp.callback_query(F.data.startswith('retry_b:'))
    async def on_retry_b(callback: CallbackQuery) -> None:
        target = callback.data.split(':', 1)[1]
        if callback.from_user:
            db.upsert_user(
                telegram_id=callback.from_user.id,
                username=callback.from_user.username,
                full_name=_full_name(callback),
                ts=now_iso(),
            )
        await callback.answer('Approfondisco Bot B...')
        await _run_with_progress(callback.message, pipeline, target, mode='bot_b', db=db)

    @dp.callback_query(F.data == 'settings')
    async def on_settings(callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.from_user and callback.from_user.id == admin_id:
            await callback.message.answer('⚙️ Versione: 1.0.0 | Stato sistema: Operativo | Admin mode: ON')
            return
        await callback.message.answer('⚙️ Versione: 1.0.0 | Stato sistema: Operativo')

    @dp.callback_query(F.data == 'reset')
    async def on_reset(callback: CallbackQuery) -> None:
        await callback.answer('Reset eseguito')
        await callback.message.answer('🗑️ Stato ricerca azzerato. Invia un nuovo @username o ID.')


async def run_frontend(bot_token: str, pipeline: SearchPipeline, db: SilentDatabase, admin_id: int) -> None:
    bot = Bot(token=bot_token)
    dp = Dispatcher()
    setup_handlers(dp, pipeline, db, admin_id)
    await dp.start_polling(bot)
