import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from dotenv import dotenv_values, load_dotenv, set_key

ENV_PATH = Path('.env')


@dataclass
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    phone_number: str


def _ensure_env_file() -> None:
    if ENV_PATH.exists():
        return

    ENV_PATH.write_text(
        'BOT_TOKEN=\n'
        'API_ID=\n'
        'API_HASH=\n'
        'PHONE_NUMBER=\n',
        encoding='utf-8',
    )


def _prompt_missing(values: Dict[str, str], key: str, label: str) -> str:
    if values.get(key):
        return str(values[key]).strip()

    user_input = ''
    while not user_input:
        user_input = input(f'Inserisci {label}: ').strip()

    set_key(str(ENV_PATH), key, user_input)
    return user_input


def load_settings() -> Settings:
    _ensure_env_file()
    load_dotenv(ENV_PATH)
    raw = dotenv_values(ENV_PATH)

    bot_token = _prompt_missing(raw, 'BOT_TOKEN', 'BOT_TOKEN (BotFather)')
    api_id = _prompt_missing(raw, 'API_ID', 'API_ID')
    api_hash = _prompt_missing(raw, 'API_HASH', 'API_HASH')
    phone_number = _prompt_missing(raw, 'PHONE_NUMBER', 'PHONE_NUMBER (+39...)')

    os.environ['BOT_TOKEN'] = bot_token
    os.environ['API_ID'] = api_id
    os.environ['API_HASH'] = api_hash
    os.environ['PHONE_NUMBER'] = phone_number

    return Settings(
        bot_token=bot_token,
        api_id=int(api_id),
        api_hash=api_hash,
        phone_number=phone_number,
    )
