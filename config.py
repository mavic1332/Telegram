from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from dotenv import dotenv_values, load_dotenv, set_key

ENV_PATH = Path('.env')


@dataclass
class Settings:
    api_id: int
    api_hash: str
    bot_token: str
    phone: str


def _ensure_env_file() -> None:
    if ENV_PATH.exists():
        return

    ENV_PATH.write_text(
        'API_ID=\n'
        'API_HASH=\n'
        'BOT_TOKEN=\n'
        'PHONE=\n',
        encoding='utf-8',
    )


def _prompt_for_key(values: Dict[str, str], key: str, prompt: str) -> str:
    current = (values.get(key) or '').strip()
    if current:
        return current

    if key == 'PHONE' and values.get('PHONE_NUMBER'):
        migrated = str(values['PHONE_NUMBER']).strip()
        set_key(str(ENV_PATH), 'PHONE', migrated)
        return migrated

    user_input = ''
    while not user_input:
        user_input = input(f'{prompt}: ').strip()

    set_key(str(ENV_PATH), key, user_input)
    return user_input


def load_settings() -> Settings:
    _ensure_env_file()
    load_dotenv(ENV_PATH)
    values = dotenv_values(ENV_PATH)

    api_id = _prompt_for_key(values, 'API_ID', 'Inserisci API_ID')
    api_hash = _prompt_for_key(values, 'API_HASH', 'Inserisci API_HASH')
    bot_token = _prompt_for_key(values, 'BOT_TOKEN', 'Inserisci BOT_TOKEN')
    phone = _prompt_for_key(values, 'PHONE', 'Inserisci PHONE (+39...)')

    return Settings(api_id=int(api_id), api_hash=api_hash, bot_token=bot_token, phone=phone)
