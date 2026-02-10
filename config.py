from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from dotenv import dotenv_values, load_dotenv, set_key

ENV_PATH = Path('.env')


@dataclass
class Settings:
    api_ids: List[int]
    api_hashes: List[str]
    bot_token: str
    admin_id: int
    userbot_phones: List[str]
    userbot_sessions: List[str]


def _ensure_env_file() -> None:
    if ENV_PATH.exists():
        return

    ENV_PATH.write_text(
        'API_ID=\n'
        'API_HASH=\n'
        'API_IDS=\n'
        'API_HASHES=\n'
        'BOT_TOKEN=\n'
        'USERBOT_PHONES=\n'
        'USERBOT_SESSIONS=sessions/acc1,sessions/acc2,sessions/acc3,sessions/acc4\n'
        'ADMIN_ID=\n',
        encoding='utf-8',
    )


def _prompt_for_key(values: Dict[str, str], key: str, prompt: str, required: bool = True) -> str:
    current = (values.get(key) or '').strip()
    if current:
        return current

    if not required:
        set_key(str(ENV_PATH), key, '')
        return ''

    user_input = ''
    while not user_input:
        user_input = input(f'{prompt}: ').strip()

    set_key(str(ENV_PATH), key, user_input)
    return user_input


def _split_csv(value: str) -> List[str]:
    items: List[str] = []
    for raw in (value or '').split(','):
        clean = raw.strip().strip('"\'').strip()
        if clean:
            items.append(clean)
    return items


def _normalize_sessions(raw_sessions: List[str], count: int) -> List[str]:
    sessions = [s for s in raw_sessions if s]
    while len(sessions) < count:
        sessions.append(f'sessions/acc{len(sessions) + 1}')
    return sessions[:count]


def _normalize_api_lists(raw_ids: List[str], raw_hashes: List[str], count: int) -> tuple[List[int], List[str]]:
    ids = [int(x) for x in raw_ids if x.isdigit()]
    hashes = [h for h in raw_hashes if h]

    if not ids:
        raise ValueError('API_IDS/API_ID non validi: inserisci almeno un API_ID numerico.')
    if not hashes:
        raise ValueError('API_HASHES/API_HASH non validi: inserisci almeno un API_HASH.')

    while len(ids) < count:
        ids.append(ids[0])
    while len(hashes) < count:
        hashes.append(hashes[0])

    return ids[:count], hashes[:count]


def load_settings() -> Settings:
    _ensure_env_file()
    load_dotenv(ENV_PATH)
    values = dotenv_values(ENV_PATH)

    # supports both single and multi API config
    api_id_single = _prompt_for_key(values, 'API_ID', 'Inserisci API_ID (fallback)', required=False)
    api_hash_single = _prompt_for_key(values, 'API_HASH', 'Inserisci API_HASH (fallback)', required=False)

    api_ids_raw = _prompt_for_key(
        values,
        'API_IDS',
        'Inserisci API_IDS (csv, es: 12345,12346) - opzionale se usi API_ID',
        required=False,
    )
    api_hashes_raw = _prompt_for_key(
        values,
        'API_HASHES',
        'Inserisci API_HASHES (csv, es: hash1,hash2) - opzionale se usi API_HASH',
        required=False,
    )

    bot_token = _prompt_for_key(values, 'BOT_TOKEN', 'Inserisci BOT_TOKEN')
    admin_id = _prompt_for_key(values, 'ADMIN_ID', 'Inserisci ADMIN_ID (opzionale)', required=False)

    phones_raw = _prompt_for_key(
        values,
        'USERBOT_PHONES',
        'Inserisci USERBOT_PHONES (csv, es: +39111,+39222 oppure singolo +39111)',
        required=False,
    )

    userbot_phones = _split_csv(phones_raw)

    # backward compatibility for old env files with PHONE / PHONE_NUMBER
    legacy_phone = (values.get('PHONE') or values.get('PHONE_NUMBER') or '').strip().strip('"\'').strip()
    if not userbot_phones and legacy_phone:
        userbot_phones = [legacy_phone]
        set_key(str(ENV_PATH), 'USERBOT_PHONES', legacy_phone)

    if not userbot_phones:
        single = _prompt_for_key(values, 'USERBOT_PHONES', 'Inserisci almeno un numero (+39...)', required=True)
        userbot_phones = _split_csv(single)

    sessions_raw = _prompt_for_key(
        values,
        'USERBOT_SESSIONS',
        'Inserisci USERBOT_SESSIONS (csv, es: sessions/acc1,sessions/acc2) - opzionale',
        required=False,
    )
    userbot_sessions = _normalize_sessions(_split_csv(sessions_raw), len(userbot_phones))
    set_key(str(ENV_PATH), 'USERBOT_SESSIONS', ','.join(userbot_sessions))

    effective_api_ids_raw = _split_csv(api_ids_raw) or ([api_id_single] if api_id_single else [])
    effective_api_hashes_raw = _split_csv(api_hashes_raw) or ([api_hash_single] if api_hash_single else [])
    api_ids, api_hashes = _normalize_api_lists(effective_api_ids_raw, effective_api_hashes_raw, len(userbot_phones))

    # persist normalized multi-account keys
    set_key(str(ENV_PATH), 'API_IDS', ','.join(str(x) for x in api_ids))
    set_key(str(ENV_PATH), 'API_HASHES', ','.join(api_hashes))

    return Settings(
        api_ids=api_ids,
        api_hashes=api_hashes,
        bot_token=bot_token,
        admin_id=int(admin_id) if admin_id.isdigit() else 0,
        userbot_phones=userbot_phones,
        userbot_sessions=userbot_sessions,
    )
