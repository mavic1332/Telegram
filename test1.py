import asyncio
import re
from pathlib import Path
from typing import Dict, List

from dotenv import dotenv_values, load_dotenv, set_key
from telethon import TelegramClient, events
from telethon.errors import (
    ChatWriteForbiddenError,
    FloodWaitError,
    UserIsBlockedError,
)

ENV_FILE = Path('.env')
ENV_TEMPLATE_FILE = Path('.env.example')
SESSION_NAME = 'test1'
TARGET_BOTS = ['@Botfindinformation_bot', '@WOW_MYAI_BOT']
COMMAND_PATTERN = re.compile(r'^/')
REQUEST_PATTERN = re.compile(r'(@[A-Za-z0-9_]{5,}|\b\d{5,}\b)')


def ensure_runtime_files() -> None:
    """Create runtime files required to start the script."""
    if not ENV_TEMPLATE_FILE.exists():
        ENV_TEMPLATE_FILE.write_text(
            'API_ID=\n'
            'API_HASH=\n'
            'PHONE_NUMBER=\n'
            'OWNER_ID=\n',
            encoding='utf-8',
        )

    if not ENV_FILE.exists():
        ENV_FILE.write_text(ENV_TEMPLATE_FILE.read_text(encoding='utf-8'), encoding='utf-8')


def ensure_credentials() -> Dict[str, str]:
    """Load credentials from .env and prompt for missing values."""
    ensure_runtime_files()
    load_dotenv(ENV_FILE)
    existing = dotenv_values(ENV_FILE)

    required_keys = {
        'API_ID': 'Telegram API ID',
        'API_HASH': 'Telegram API HASH',
        'PHONE_NUMBER': 'Telegram phone number (include country code)',
    }

    for key, label in required_keys.items():
        if not existing.get(key):
            value = ''
            while not value:
                value = input(f'Enter {label}: ').strip()
            set_key(str(ENV_FILE), key, value)
            existing[key] = value

    if not existing.get('OWNER_ID'):
        set_key(str(ENV_FILE), 'OWNER_ID', '')

    return {
        'api_id': existing['API_ID'],
        'api_hash': existing['API_HASH'],
        'phone': existing['PHONE_NUMBER'],
        'owner_id': (existing.get('OWNER_ID') or '').strip(),
    }


def clean_text(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r'@Botfindinformation_bot', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'@WOW_MYAI_BOT', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(?im)^.*powered by.*$', '', cleaned)
    cleaned = re.sub(r'(?im)^.*join\s+channel.*$', '', cleaned)
    cleaned = re.sub(r'https?://t\.me/\S+', '', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def dedupe_lines(text: str) -> List[str]:
    seen = set()
    result = []
    for raw_line in text.splitlines():
        line = raw_line.strip('•- \t')
        if not line:
            continue

        dedupe_key = re.sub(r'\s+', ' ', line).strip().lower()
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        result.append(line)
    return result


def emoji_label(line: str) -> str:
    lower = line.lower()
    if 'name' in lower or 'username' in lower:
        return '👤'
    if 'phone' in lower or re.search(r'\+?\d{7,}', line):
        return '📞'
    if 'id' in lower:
        return '🆔'
    if 'location' in lower or 'address' in lower:
        return '📍'
    if 'email' in lower:
        return '📧'
    return '📌'


def format_result(lines: List[str]) -> str:
    if not lines:
        return '⚠️ No clean data was returned by the source bots.'

    formatted = ['✅ *Search Complete*\n']
    for line in lines:
        formatted.append(f"{emoji_label(line)} {line}")
    return '\n'.join(formatted)


async def query_bot(client: TelegramClient, bot_username: str, payload: str) -> str:
    """Send payload to bot and return first textual response."""
    try:
        async with client.conversation(bot_username, timeout=40) as conv:
            await conv.send_message(payload)
            response = await conv.get_response()
            return response.raw_text or ''
    except asyncio.TimeoutError:
        return f'⚠️ {bot_username}: timeout waiting for response.'
    except (UserIsBlockedError, ChatWriteForbiddenError):
        return f'⚠️ {bot_username}: bot is blocked or cannot be messaged.'
    except FloodWaitError as exc:
        return f'⚠️ {bot_username}: flood wait for {exc.seconds}s.'
    except Exception as exc:  # noqa: BLE001
        return f'⚠️ {bot_username}: unexpected error ({exc}).'


async def main() -> None:
    creds = ensure_credentials()
    client = TelegramClient(SESSION_NAME, int(creds['api_id']), creds['api_hash'])

    await client.start(phone=creds['phone'])
    me = await client.get_me()

    owner_id = int(creds['owner_id']) if creds['owner_id'].isdigit() else me.id

    print(f'Logged in as: {me.first_name} ({me.id})')
    print('Middleware UserBot is running...')

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def middleware_handler(event: events.NewMessage.Event) -> None:
        sender = await event.get_sender()
        sender_id = sender.id if sender else None
        text = (event.raw_text or '').strip()

        if not text:
            return

        if COMMAND_PATTERN.match(text) and sender_id != owner_id:
            return

        match = REQUEST_PATTERN.search(text)
        if not match:
            return

        payload = match.group(1)
        status_msg = await event.reply('🔎 Searching...')

        responses = await asyncio.gather(*(query_bot(client, bot, payload) for bot in TARGET_BOTS))

        merged = clean_text('\n'.join(responses))
        lines = dedupe_lines(merged)
        final_message = format_result(lines)

        await status_msg.edit(final_message)

    await client.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nStopped by user.')
