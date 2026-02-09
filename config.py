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
    admin_id: int


def _ensure_env_file() -> None:
    if ENV_PATH.exists():
        return

    ENV_PATH.write_text(
        'API_ID=\n'
        'API_HASH=\n'
        'BOT_TOKEN=\n'
        'PHONE=\n'
        'ADMIN_ID=\n',
        encoding='utf-8',
    )


def _prompt_for_key(values: Dict[str, str], key: str, prompt: str, required: bool = True) -> str:
    current = (values.get(key) or '').strip()
    if current:
        return current

    if key == 'PHONE' and values.get('PHONE_NUMBER'):
        migrated = str(values['PHONE_NUMBER']).strip()
        set_key(str(ENV_PATH), 'PHONE', migrated)
        return migrated

    if not required:
        set_key(str(ENV_PATH), key, '')
        return ''

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
    admin_id = _prompt_for_key(values, 'ADMIN_ID', 'Inserisci ADMIN_ID (opzionale)', required=False)

    return Settings(
        api_id=int(api_id),
        api_hash=api_hash,
        bot_token=bot_token,
        phone=phone,
        admin_id=int(admin_id) if admin_id.isdigit() else 0,
    )
