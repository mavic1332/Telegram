from __future__ import annotations

import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.audit import AuditLogger
from app.pipeline import Pipeline
from app.security import RateLimiter, is_chat_allowed, mask_identifier
from app.utils import USERNAME_RE, parse_identifier

logger = logging.getLogger(__name__)

pipeline = Pipeline()
audit = AuditLogger()
rate_limiter = RateLimiter(cooldown_seconds=3)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return
    if not is_chat_allowed(update.effective_chat.id):
        return
    await update.message.reply_text(
        "Ciao! Questo bot recupera informazioni dal VoIP.\n"
        "Scrivi un numero di telefono oppure una @username (es: @ciao1234)."
    )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    if not is_chat_allowed(chat_id):
        return
    if not rate_limiter.allow(chat_id):
        await update.message.reply_text("Attendi qualche secondo prima di una nuova richiesta.")
        return

    raw = update.message.text.strip()
    try:
        normalized, _kind = parse_identifier(raw)
    except ValueError:
        await update.message.reply_text("Input non valido. Inserisci un telefono o una @username valida.")
        return

    context.user_data["raw_input"] = raw
    context.user_data["normalized_identifier"] = normalized

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Telegram", callback_data="search:Telegram")],
         [InlineKeyboardButton("Instagram", callback_data="search:Instagram")],
         [InlineKeyboardButton("Tiktok", callback_data="search:Tiktok")]]
    )
    await update.message.reply_text(
        f"🔎 Identificatore rilevato: {normalized}\nScegli il tipo di ricerca:", reply_markup=keyboard
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    await query.answer()

    if query.data == "new_search":
        context.user_data.clear()
        await query.edit_message_text("Sessione resettata. Invia un numero di telefono o una @username.")
        return

    if not query.data or not query.data.startswith("search:"):
        return

    search_type = query.data.split(":", 1)[1]
    context.user_data["search_type"] = search_type
    normalized_identifier = context.user_data.get("normalized_identifier")
    if not normalized_identifier:
        await query.edit_message_text("Sessione scaduta. Invia di nuovo l'identificatore.")
        return

    msg = await query.edit_message_text("⏳ Sto cercando, attendi…")

    async def progress_cb(text: str) -> None:
        await msg.edit_text(text)

    start = time.monotonic()
    try:
        result = await pipeline.run(normalized_identifier, search_type, progress_cb)
        counters = "\n".join([f"- {k}: {v}" for k, v in result.counters.items()]) or "- N/D"
        history = "\n".join([f"- {entry}" for entry in result.history]) or "- N/D"
        created_at = result.created_at.isoformat() if result.created_at else "N/D"

        response = (
            f"✅ Risultato (tipo: {result.search_type})\n"
            f"👤 Identificatore: {result.identifier_input}\n"
            f"🆔 ID: {result.canonical_id}\n"
            f"🗓️ Registrazione: {created_at}\n\n"
            f"🙍 Nome: {result.display_name or 'N/D'}\n"
            f"📞 Telefono: {result.phone or 'N/D'}\n\n"
            f"📊 Dati:\n{counters}\n\n"
            f"🕒 Storico:\n{history}\n"
        )
        if result.notes:
            response += f"\nℹ️ {result.notes}"

        buttons = [[InlineKeyboardButton("🔁 Nuova ricerca", callback_data="new_search")]]
        if search_type == "Telegram" and USERNAME_RE.match(normalized_identifier):
            buttons.append([InlineKeyboardButton("💬 Apri dialogo", url=f"https://t.me/{normalized_identifier[1:]}")])

        await msg.edit_text(response, reply_markup=InlineKeyboardMarkup(buttons))
        audit.log(chat_id, search_type, "success", int((time.monotonic() - start) * 1000))
    except Exception:  # noqa: BLE001
        logger.exception("Pipeline error id=%s", mask_identifier(normalized_identifier))
        await msg.edit_text("Non sono riuscito a completare la ricerca. Riprova più tardi.")
        audit.log(chat_id, search_type, "error", int((time.monotonic() - start) * 1000))


def build_app(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    return app
