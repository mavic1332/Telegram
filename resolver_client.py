import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable, Optional, Tuple

from telethon import TelegramClient, events
from telethon.errors import ChatWriteForbiddenError, FloodWaitError, UserIsBlockedError
from telethon.tl.custom.message import Message

from models import RawBotResponses, UserProfile

BOT_A = '@Botfindinformation_bot'
MAX_BOT_WAIT_S = 60
PRIORITY_DELIVERY_S = 15
LIMIT_HOURS = 12
ROTATION_COOLDOWN_S = 2
ROTATION_GRACE_S = 8
ROTATION_EXTENSION_S = 15
WAITING_LOG_INTERVAL_S = 10
WAIT_UNTIL_RE = re.compile(r'new\s+requests\s+will\s+be\s+granted\s+at\s*(\d{1,2}:\d{2})', re.IGNORECASE)
COUNTDOWN_RE = re.compile(r'\b(\d{2}:\d{2})\b')
ProgressCb = Optional[Callable[[str], Awaitable[None]]]
LIMIT_RE = re.compile(
    r'(?:you\s+have\s+reached\s+the\s+daily\s+limit|daily\s+limit\s+reached|no\s+credits|limit\s+reached|'
    r'ваш\s+лимит\s+запросов\s+временно\s+исчерпан|чтобы\s+продолжить\s+поиск,?\s*вы\s+можете\s+купить|'
    r'лимит|rate\s*limit|wait\s*\d+\s*[hm]|attendi\s*\d+\s*[hm])',
    re.IGNORECASE,
)
ProfileUpdater = Optional[Callable[[str, str, int], None]]


@dataclass
class ResolverClient:
    api_ids: list[int]
    api_hashes: list[str]
    phones: list[str]
    session_names: list[str]
    target_bot_b: str = "@peoepeoeAIbot"

    def __post_init__(self) -> None:
        if not self.phones:
            raise ValueError('At least one phone is required for userbot clients.')

        while len(self.session_names) < len(self.phones):
            self.session_names.append(f'sessions/acc{len(self.session_names) + 1}')

        while len(self.api_ids) < len(self.phones):
            self.api_ids.append(self.api_ids[0])
        while len(self.api_hashes) < len(self.phones):
            self.api_hashes.append(self.api_hashes[0])

        if len(set(self.api_ids)) == 1 and len(set(self.api_hashes)) == 1 and len(self.phones) > 1:
            logging.warning('[WARN] Single API_ID/API_HASH reused across %d accounts; possible flood limitations.', len(self.phones))

        self._clients: list[TelegramClient] = []
        for idx, session in enumerate(self.session_names[:len(self.phones)]):
            Path(session).parent.mkdir(parents=True, exist_ok=True)
            self._clients.append(TelegramClient(session, self.api_ids[idx], self.api_hashes[idx]))

        self._primary_client = self._clients[0]
        self._phone_cache: dict[str, str] = {}
        self._limited_until: dict[int, datetime] = {}
        self._last_rotation_at: Optional[float] = None
        self._active_bot_b_started: Optional[float] = None
        self._bot_b_pending: dict[int, tuple[asyncio.Future[Tuple[str, float]], Optional[Callable[[str], bool]], float, int, ProfileUpdater]] = {}
        self._bot_b_handlers: dict[int, Callable] = {}
        self._listener_busy = 0

    async def start(self) -> None:
        for idx, (client, phone) in enumerate(zip(self._clients, self.phones), start=1):
            await client.start(phone=phone)
            logging.info('[STATUS] Account %d initialized (%s).', idx, self.session_names[idx - 1])
            try:
                await client.send_message(self.target_bot_b, '/start')
                logging.info('[STATUS] Account %d startup check OK -> %s', idx, self.target_bot_b)
            except Exception as exc:  # noqa: BLE001
                logging.warning('[STATUS] Account %d startup check FAILED -> %s (%s)', idx, self.target_bot_b, exc)

            async def on_new_message(event: events.NewMessage.Event, account_idx: int = idx) -> None:
                pending = self._bot_b_pending.get(account_idx)
                if not pending:
                    return
                future, predicate, started_at, bot_chat_id, profile_updater = pending
                if future.done():
                    return
                text = (event.raw_text or '').strip()
                if not text:
                    return
                if event.chat_id != bot_chat_id:
                    return
                if predicate and not predicate(text):
                    return
                logging.info('[LISTENER] Capturing response for %s on Account %d...', self.target_bot_b, account_idx)
                self._listener_busy += 1
                try:
                    if self._is_limit_message(text):
                        future.set_result((text, max(0.01, time.perf_counter() - started_at)))
                        return
                    parsed = self._apply_regex_enrichment('b', text)
                    if profile_updater:
                        profile_updater('bot_b', parsed, account_idx)
                    future.set_result((parsed, max(0.01, time.perf_counter() - started_at)))
                finally:
                    self._listener_busy = max(0, self._listener_busy - 1)

            self._bot_b_handlers[idx] = on_new_message
            client.add_event_handler(on_new_message, events.NewMessage())

    async def stop(self) -> None:
        for idx, client in enumerate(self._clients, start=1):
            handler = self._bot_b_handlers.get(idx)
            if handler:
                client.remove_event_handler(handler)
            await client.disconnect()

    async def fetch_info(self, target: str, mode: str = 'all', progress_cb: ProgressCb = None) -> RawBotResponses:
        profile = UserProfile(phone=self._phone_cache.get(target))

        def update_profile(bot_name: str, payload: str, account_idx: int) -> None:
            updated_fields = self._merge_profile(profile, bot_name, payload)
            if updated_fields:
                logging.info('[DATA_SYNC] Fields updated by Account %d: %s', account_idx, ', '.join(updated_fields))

        if mode == 'bot_a':
            text_a, wait_a, retry_after, sec_a = await self._query_botfind(target, progress_cb=progress_cb, profile_updater=update_profile)
            await self._wait_for_listener_sync()
            return RawBotResponses(
                botfindinformation=text_a,
                bot_a_wait_until=wait_a,
                bot_a_retry_after=retry_after,
                bot_a_seconds=sec_a,
                bot_a_phone=profile.phone,
                profile=profile,
            )

        if mode == 'bot_b':
            text_b, sec_b = await self._query_wow_rotating(target, progress_cb=progress_cb, profile_updater=update_profile)
            await self._wait_for_listener_sync()
            return RawBotResponses(wow_myai=text_b, bot_b_seconds=sec_b, bot_a_phone=profile.phone, profile=profile)

        started = time.perf_counter()
        task_a = asyncio.create_task(self._query_botfind(target, progress_cb=progress_cb, profile_updater=update_profile))
        task_b = asyncio.create_task(self._query_wow_rotating(target, progress_cb=progress_cb, profile_updater=update_profile))

        text_a, wait_a, retry_after, sec_a = ('Timeout su Bot A.', None, None, None)
        text_b, sec_b = ('Timeout su Bot B.', None)
        bot_b_terminal = False
        self._last_rotation_at = None
        self._active_bot_b_started = started
        priority_deadline = started + PRIORITY_DELIVERY_S
        deadline = started + MAX_BOT_WAIT_S
        seen_rotation_at: Optional[float] = None
        last_waiting_bucket = -1

        while True:
            elapsed = time.perf_counter() - started
            pending_names = []
            if not task_a.done():
                pending_names.append('Bot A')
            if not task_b.done() and not bot_b_terminal:
                pending_names.append('Bot B')
            if pending_names:
                waiting_bucket = int(elapsed // WAITING_LOG_INTERVAL_S)
                if waiting_bucket > 0 and waiting_bucket != last_waiting_bucket:
                    last_waiting_bucket = waiting_bucket
                    logging.info('[WAITING] for %s... (%ds elapsed)', ' and '.join(pending_names), waiting_bucket * WAITING_LOG_INTERVAL_S)

            if self._last_rotation_at and self._last_rotation_at != seen_rotation_at:
                seen_rotation_at = self._last_rotation_at
                priority_deadline = seen_rotation_at + PRIORITY_DELIVERY_S
                deadline = max(deadline, seen_rotation_at + ROTATION_EXTENSION_S)
                logging.info('[ROTATION] Timer reset: nuova finestra prioritaria %ss per account attivo.', PRIORITY_DELIVERY_S)
                logging.info('[ROTATION] Timeout esteso: deadline aggiornata (+%ss per account attivo).', ROTATION_EXTENSION_S)

            if self._active_bot_b_started and self._active_bot_b_started > started and self._active_bot_b_started + PRIORITY_DELIVERY_S > priority_deadline:
                priority_deadline = self._active_bot_b_started + PRIORITY_DELIVERY_S

            if self._has_core_profile(profile) and not task_a.done():
                task_a.cancel()
                sec_a = sec_a or max(0.01, elapsed)
                logging.info('[STATUS] Bot A completo (ID+Telefono). Focus su Bot B/rotazione.')

            done, _ = await asyncio.wait({task_a, task_b}, timeout=1, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is task_a and text_a == 'Timeout su Bot A.':
                    try:
                        text_a, wait_a, retry_after, sec_a = task.result()
                    except Exception:
                        text_a, wait_a, retry_after, sec_a = ('Timeout su Bot A.', None, None, max(0.01, elapsed))
                elif task is task_b and text_b == 'Timeout su Bot B.':
                    try:
                        text_b, sec_b = task.result()
                    except Exception:
                        text_b, sec_b = ('Timeout su Bot B.', max(0.01, elapsed))
                    if self._is_bot_b_error(text_b):
                        bot_b_terminal = True

            if task_a.done() and (task_b.done() or bot_b_terminal):
                break

            if time.perf_counter() >= deadline:
                if not task_a.done():
                    task_a.cancel()
                    sec_a = max(0.01, elapsed)
                if not task_b.done():
                    task_b.cancel()
                    sec_b = max(0.01, elapsed)
                break

        if sec_a is None:
            sec_a = max(0.01, time.perf_counter() - started)
        if sec_b is None:
            sec_b = max(0.01, time.perf_counter() - started)

        if profile.phone:
            self._phone_cache[target] = profile.phone

        return RawBotResponses(
            botfindinformation=text_a,
            wow_myai=text_b,
            bot_a_wait_until=wait_a,
            bot_a_retry_after=retry_after,
            bot_a_seconds=sec_a,
            bot_b_seconds=sec_b,
            bot_a_phone=profile.phone,
            profile=profile,
        )

    async def _wait_for_listener_sync(self, timeout_s: float = 3.0) -> None:
        end = time.perf_counter() + timeout_s
        while self._listener_busy > 0 and time.perf_counter() < end:
            await asyncio.sleep(0.05)

    def _available_rotation_indexes(self) -> list[int]:
        now = datetime.utcnow()
        available: list[int] = []
        for idx in range(len(self._clients)):
            limited = self._limited_until.get(idx)
            if not limited or limited <= now:
                available.append(idx)
        logging.info('[STATUS] %d/%d accounts available.', len(available), len(self._clients))
        return available

    async def _query_wow_rotating(
        self,
        target: str,
        progress_cb: ProgressCb = None,
        profile_updater: ProfileUpdater = None,
    ) -> Tuple[str, float]:
        started = time.perf_counter()
        available = self._available_rotation_indexes()
        if not available:
            return 'Tutti gli account Bot B sono temporaneamente limitati.', max(0.01, time.perf_counter() - started)

        for pos, idx in enumerate(available, start=1):
            client = self._clients[idx]
            self._active_bot_b_started = time.perf_counter()
            logging.info('[STATUS] Account %d attivo per Bot B: finestra ascolto %ss.', idx + 1, PRIORITY_DELIVERY_S)
            text, sec = await self._query_wow_with_client(client, idx + 1, target, progress_cb=progress_cb, profile_updater=profile_updater)
            if self._is_bot_b_error(text):
                self._limited_until[idx] = datetime.utcnow() + timedelta(hours=LIMIT_HOURS)
                logging.info('[ROTATION] Account %d marked LIMIT_REACHED, forcing switch.', idx + 1)
                if pos < len(available):
                    next_idx = available[pos]
                    logging.info('[ROTATION] Account %d limited, switching to Account %d...', idx + 1, next_idx + 1)
                    self._last_rotation_at = time.perf_counter()
                    logging.info('[STATUS] %d/%d accounts available.', len(self._available_rotation_indexes()), len(self._clients))
                    await asyncio.sleep(ROTATION_COOLDOWN_S)
                continue
            return text, sec

        return 'Limite raggiunto su tutti gli account Bot B disponibili.', max(0.01, time.perf_counter() - started)

    async def _query_wow_with_client(
        self,
        client: TelegramClient,
        account_idx: int,
        target: str,
        progress_cb: ProgressCb = None,
        profile_updater: ProfileUpdater = None,
    ) -> Tuple[str, float]:
        started = time.perf_counter()
        try:
            entity = await client.get_entity(self.target_bot_b)
            loop = asyncio.get_running_loop()
            done_future: asyncio.Future[Tuple[str, float]] = loop.create_future()
            self._bot_b_pending[account_idx] = (done_future, self._is_terminal_bot_b_message, time.perf_counter(), entity.id, profile_updater)
            logging.info('[LISTENER] Armed global listener for Account %d -> %s (chat=%s).', account_idx, self.target_bot_b, entity.id)
            await client.send_message(entity, target)
            try:
                text, sec_b = await asyncio.wait_for(done_future, timeout=MAX_BOT_WAIT_S)
            finally:
                self._bot_b_pending.pop(account_idx, None)
            if progress_cb:
                await progress_cb('bot_b')
            return text, sec_b
        except asyncio.TimeoutError:
            return 'Timeout su Bot B.', max(0.01, time.perf_counter() - started)
        except (UserIsBlockedError, ChatWriteForbiddenError):
            return 'Bot B bloccato o non scrivibile.', max(0.01, time.perf_counter() - started)
        except FloodWaitError as exc:
            return f'Flood wait Bot B: {exc.seconds}s.', max(0.01, time.perf_counter() - started)
        except Exception as exc:  # noqa: BLE001
            return f'Errore Bot B: {exc}', max(0.01, time.perf_counter() - started)

    @staticmethod
    def _has_core_profile(profile: UserProfile) -> bool:
        return bool(profile.identifier and profile.phone)

    @staticmethod
    def _is_limit_message(text: str) -> bool:
        return bool(LIMIT_RE.search(text or ''))

    @staticmethod
    def _is_bot_b_error(text: str) -> bool:
        lowered = (text or '').lower()
        return bool(LIMIT_RE.search(lowered) or 'timeout su bot b' in lowered or 'errore bot b' in lowered)

    async def _query_botfind(
        self,
        target: str,
        progress_cb: ProgressCb = None,
        profile_updater: ProfileUpdater = None,
    ) -> Tuple[str, Optional[str], Optional[str], float]:
        started = time.perf_counter()
        try:
            async with self._primary_client.conversation(BOT_A, timeout=MAX_BOT_WAIT_S) as conv:
                await conv.send_message(target)
                menu_msg = await conv.get_response()
                menu_text = (menu_msg.raw_text or '').lower()
                has_direction = ('choose direction' in menu_text) or ('направлен' in menu_text)

                if has_direction and menu_msg.buttons:
                    clicked = False
                    for row in menu_msg.buttons:
                        for button in row:
                            if 'telegram' in (button.text or '').lower():
                                await menu_msg.click(text=button.text)
                                clicked = True
                                if progress_cb:
                                    await progress_cb('bot_a_clicked')
                                break
                        if clicked:
                            break
                    if not clicked:
                        await menu_msg.click(0)
                        if progress_cb:
                            await progress_cb('bot_a_clicked')
                    result_msg: Message = await conv.get_response()
                    result_text = result_msg.raw_text or ''
                else:
                    result_text = menu_msg.raw_text or ''

                sec_a = max(0.01, time.perf_counter() - started)
                wait_until = self._extract_wait_time(result_text)
                retry_after = self._extract_countdown(result_text)
                parsed = self._apply_regex_enrichment('a', result_text)

                if profile_updater:
                    profile_updater('bot_a', parsed, 1)

                phone = self._extract_phone(parsed)
                if phone:
                    self._phone_cache[target] = phone

                if progress_cb:
                    await progress_cb('bot_a')

                if wait_until or retry_after:
                    return '', wait_until, retry_after, sec_a
                return parsed, None, None, sec_a
        except asyncio.TimeoutError:
            return 'Timeout su Bot A.', None, None, max(0.01, time.perf_counter() - started)
        except (UserIsBlockedError, ChatWriteForbiddenError):
            return 'Bot A bloccato o non scrivibile.', None, None, max(0.01, time.perf_counter() - started)
        except FloodWaitError as exc:
            return f'Flood wait Bot A: {exc.seconds}s.', None, None, max(0.01, time.perf_counter() - started)
        except Exception as exc:  # noqa: BLE001
            return f'Errore Bot A: {exc}', None, None, max(0.01, time.perf_counter() - started)

    @staticmethod
    def _is_terminal_bot_b_message(text: str) -> bool:
        lowered = (text or '').lower()
        if '%' in text or 'searching' in lowered:
            return False
        return ('search by telegram id' in lowered) or bool(LIMIT_RE.search(lowered))

    @staticmethod
    def _extract_wait_time(text: str) -> Optional[str]:
        match = WAIT_UNTIL_RE.search(text or '')
        return match.group(1) if match else None

    @staticmethod
    def _extract_countdown(text: str) -> Optional[str]:
        match = COUNTDOWN_RE.search(text or '')
        return match.group(1) if match else None

    @staticmethod
    def _extract_phone(text: str) -> Optional[str]:
        line = re.search(r'(?im)^.*(?:Телефон\s*:|📞)\s*([^\n\r]+)$', text or '')
        if line:
            match = re.search(r'(\d{10,13})', line.group(1))
            if match:
                return match.group(1)
        fallback = re.search(r'(?<!\d)(\d{10,13})(?!\d)', text or '')
        return fallback.group(1) if fallback else None

    @staticmethod
    def _apply_regex_enrichment(source: str, text: str) -> str:
        payload = text or ''
        if source == 'a':
            found_id = re.search(r'(?im)\bID\s*:\s*(\d+)', payload)
            found_phone = re.search(r'(?is)(?:Телефон\s*:|📞\s*)(\d{10,})', payload)
            parts = []
            if found_id:
                parts.append(f'ID: {found_id.group(1)}')
            if found_phone:
                parts.append(f'📞 Телефон: {found_phone.group(1)}')
            return ('\n'.join(parts) + '\n' + payload) if parts else payload

        found_search = re.search(r'(?im)^\s*Search\s+by\s+Telegram\s+ID\s+.*?(\d+)\s*$', payload)
        found_registered_block = re.search(r'(?is)Registered\s*\n\s*([^\n\r]+(?:\n[^\n\r]+)*)', payload)
        parts = []
        if found_search:
            parts.append(f'Search by Telegram ID {found_search.group(1)}')
        if found_registered_block:
            reg_text = found_registered_block.group(1).split('🤖 Bots')[0].strip()
            parts.append('Registered')
            parts.append(reg_text)
        return ('\n'.join(parts) + '\n' + payload) if parts else payload

    @staticmethod
    def _merge_profile(profile: UserProfile, bot_name: str, text: str) -> list[str]:
        payload = text or ''
        if not payload:
            return []

        updated_fields: list[str] = []
        id_match = re.search(r'(?im)\bID\s*:\s*(\d+)', payload)
        if not id_match:
            id_match = re.search(r'(?im)^\s*Search\s+by\s+Telegram\s+ID\s+.*?(\d+)\s*$', payload)
        if id_match and not profile.identifier:
            profile.identifier = id_match.group(1)
            updated_fields.append('ID')

        phone_match = re.search(r'(?im)^.*(?:Телефон\s*:|📞)\s*[^\n\r]*(\d{10,13})', payload)
        if phone_match and not profile.phone:
            profile.phone = phone_match.group(1)
            updated_fields.append('Telefono')

        reg_match = re.search(r'(?is)\bRegistered\b\s*:?\s*(.*?)(?:\n\s*🤖\s*Bots\b|$)', payload)
        if reg_match and not profile.registration:
            lines = [ln.strip() for ln in re.split(r'\r?\n', reg_match.group(1)) if ln.strip()]
            clean_dates = [
                ln for ln in lines
                if 'search by telegram id' not in ln.lower() and not re.fullmatch(r'\d{7,10}', re.sub(r'\D', '', ln))
            ]
            if clean_dates:
                profile.registration = ', '.join(clean_dates)
                updated_fields.append('Registrazione')

        if bot_name == 'bot_a':
            groups = re.findall(r'@[A-Za-z0-9_]{3,}', payload)
            for group in groups:
                if group not in profile.groups:
                    profile.groups.append(group)
                    if 'Gruppi' not in updated_fields:
                        updated_fields.append('Gruppi')
            hist_block = re.search(r'(?is)История\s+изменения\s+имени\s*:\s*(.*?)\s*👥\s*Группы\s*:', payload)
            if hist_block:
                for ln in re.split(r'\r?\n', hist_block.group(1)):
                    val = ln.strip('•- \t>')
                    if val and val not in profile.history:
                        profile.history.append(val)
                        if 'Storico' not in updated_fields:
                            updated_fields.append('Storico')

        if bot_name == 'bot_b':
            bots_block = re.search(r'(?is)🤖\s*Bots\s*(.*)$', payload)
            if bots_block:
                for ln in re.split(r'\r?\n', bots_block.group(1)):
                    val = ln.strip('•- \t>')
                    if ':' in val and val not in profile.bot_data:
                        profile.bot_data.append(val)
                        if 'Dati' not in updated_fields:
                            updated_fields.append('Dati')

        return updated_fields
