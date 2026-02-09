import asyncio
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Tuple

from telethon import TelegramClient, events
from telethon.errors import ChatWriteForbiddenError, FloodWaitError, UserIsBlockedError
from telethon.tl.custom.message import Message

from models import RawBotResponses, UserProfile

BOT_A = '@Botfindinformation_bot'
BOT_B = '@WOW_MYAI_BOT'
MAX_BOT_WAIT_S = 60
WAIT_UNTIL_RE = re.compile(r'new\s+requests\s+will\s+be\s+granted\s+at\s*(\d{1,2}:\d{2})', re.IGNORECASE)
COUNTDOWN_RE = re.compile(r'\b(\d{2}:\d{2})\b')
ProgressCb = Optional[Callable[[str], Awaitable[None]]]
LIMIT_RE = re.compile(r'(?:daily\s+limit\s+reached|limit\s+reached|лимит|rate\s*limit)', re.IGNORECASE)


@dataclass
class ResolverClient:
    api_id: int
    api_hash: str
    phone: str
    session_name: str = 'test1_resolver'

    def __post_init__(self) -> None:
        self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
        self._phone_cache: dict[str, str] = {}

    async def start(self) -> None:
        await self.client.start(phone=self.phone)

    async def stop(self) -> None:
        await self.client.disconnect()

    async def fetch_info(self, target: str, mode: str = 'all', progress_cb: ProgressCb = None) -> RawBotResponses:
        profile = UserProfile(phone=self._phone_cache.get(target))

        if mode == 'bot_a':
            text_a, wait_a, retry_after, sec_a = await self._query_botfind(target, progress_cb=progress_cb)
            self._merge_profile(profile, 'bot_a', text_a)
            return RawBotResponses(
                botfindinformation=text_a,
                bot_a_wait_until=wait_a,
                bot_a_retry_after=retry_after,
                bot_a_seconds=sec_a,
                bot_a_phone=profile.phone,
                profile=profile,
            )

        if mode == 'bot_b':
            text_b, sec_b = await self._query_wow(target, progress_cb=progress_cb)
            self._merge_profile(profile, 'bot_b', text_b)
            return RawBotResponses(wow_myai=text_b, bot_b_seconds=sec_b, bot_a_phone=profile.phone, profile=profile)

        bot_jobs = {
            'bot_a': asyncio.create_task(self._query_botfind(target, progress_cb=progress_cb)),
            'bot_b': asyncio.create_task(self._query_wow(target, progress_cb=progress_cb)),
        }

        text_a, wait_a, retry_after, sec_a = ('Timeout su Bot A.', None, None, None)
        text_b, sec_b = ('Timeout su Bot B.', None)

        done, pending = await asyncio.wait(set(bot_jobs.values()), timeout=MAX_BOT_WAIT_S)
        for task in done:
            bot_name = 'bot_a' if task is bot_jobs['bot_a'] else 'bot_b'
            try:
                result = task.result()
            except Exception:
                if bot_name == 'bot_a':
                    result = ('Timeout su Bot A.', None, None, MAX_BOT_WAIT_S)
                else:
                    result = ('Timeout su Bot B.', MAX_BOT_WAIT_S)

            if bot_name == 'bot_a':
                text_a, wait_a, retry_after, sec_a = result
                self._merge_profile(profile, bot_name, text_a)
            else:
                text_b, sec_b = result
                self._merge_profile(profile, bot_name, text_b)

        for task in pending:
            task.cancel()

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

    async def _listen_first_text(self, chat_id: int, timeout: int, predicate: Optional[Callable[[str], bool]] = None) -> Tuple[str, float]:
        loop = asyncio.get_running_loop()
        start = time.perf_counter()
        done_future: asyncio.Future[Tuple[str, float]] = loop.create_future()

        async def on_new_message(event: events.NewMessage.Event) -> None:
            text = (event.raw_text or '').strip()
            if not text or done_future.done():
                return
            if predicate and not predicate(text):
                return
            done_future.set_result((text, max(0.001, time.perf_counter() - start)))

        event_filter = events.NewMessage(chats=[chat_id])
        self.client.add_event_handler(on_new_message, event_filter)
        try:
            return await asyncio.wait_for(done_future, timeout=timeout)
        finally:
            self.client.remove_event_handler(on_new_message, event_filter)

    async def _query_botfind(self, target: str, progress_cb: ProgressCb = None) -> Tuple[str, Optional[str], Optional[str], float]:
        started = time.perf_counter()
        try:
            async with self.client.conversation(BOT_A, timeout=MAX_BOT_WAIT_S) as conv:
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

                sec_a = max(0.001, time.perf_counter() - started)
                wait_until = self._extract_wait_time(result_text)
                retry_after = self._extract_countdown(result_text)
                parsed = self._apply_regex_enrichment('a', result_text)

                phone = self._extract_phone(parsed)
                if phone:
                    self._phone_cache[target] = phone

                if progress_cb:
                    await progress_cb('bot_a')

                if wait_until or retry_after:
                    return '', wait_until, retry_after, sec_a
                return parsed, None, None, sec_a
        except asyncio.TimeoutError:
            return 'Timeout su Bot A.', None, None, max(0.001, time.perf_counter() - started)
        except (UserIsBlockedError, ChatWriteForbiddenError):
            return 'Bot A bloccato o non scrivibile.', None, None, max(0.001, time.perf_counter() - started)
        except FloodWaitError as exc:
            return f'Flood wait Bot A: {exc.seconds}s.', None, None, max(0.001, time.perf_counter() - started)
        except Exception as exc:  # noqa: BLE001
            return f'Errore Bot A: {exc}', None, None, max(0.001, time.perf_counter() - started)

    async def _query_wow(self, target: str, progress_cb: ProgressCb = None) -> Tuple[str, float]:
        started = time.perf_counter()
        try:
            entity = await self.client.get_entity(BOT_B)
            await self.client.send_message(entity, target)
            text, sec_b = await self._listen_first_text(entity.id, MAX_BOT_WAIT_S, predicate=self._is_terminal_bot_b_message)
            parsed = self._apply_regex_enrichment('b', text)
            if progress_cb:
                await progress_cb('bot_b')
            return parsed, sec_b
        except asyncio.TimeoutError:
            return 'Timeout su Bot B.', max(0.001, time.perf_counter() - started)
        except (UserIsBlockedError, ChatWriteForbiddenError):
            return 'Bot B bloccato o non scrivibile.', max(0.001, time.perf_counter() - started)
        except FloodWaitError as exc:
            return f'Flood wait Bot B: {exc.seconds}s.', max(0.001, time.perf_counter() - started)
        except Exception as exc:  # noqa: BLE001
            return f'Errore Bot B: {exc}', max(0.001, time.perf_counter() - started)

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
    def _merge_profile(profile: UserProfile, bot_name: str, text: str) -> None:
        payload = text or ''
        if not payload:
            return

        id_match = re.search(r'(?im)\bID\s*:\s*(\d+)', payload)
        if not id_match:
            id_match = re.search(r'(?im)^\s*Search\s+by\s+Telegram\s+ID\s+.*?(\d+)\s*$', payload)
        if id_match and not profile.identifier:
            profile.identifier = id_match.group(1)

        phone_match = re.search(r'(?im)^.*(?:Телефон\s*:|📞)\s*[^\n\r]*(\d{10,13})', payload)
        if phone_match and not profile.phone:
            profile.phone = phone_match.group(1)

        reg_match = re.search(r'(?is)\bRegistered\b\s*:?\s*(.*?)(?:\n\s*🤖\s*Bots\b|$)', payload)
        if reg_match and not profile.registration:
            lines = [ln.strip() for ln in re.split(r'\r?\n', reg_match.group(1)) if ln.strip()]
            clean_dates = [ln for ln in lines if 'search by telegram id' not in ln.lower() and not re.fullmatch(r'\d{7,10}', re.sub(r'\D', '', ln))]
            if clean_dates:
                profile.registration = ', '.join(clean_dates)

        if bot_name == 'bot_a':
            groups = re.findall(r'@[A-Za-z0-9_]{3,}', payload)
            for group in groups:
                if group not in profile.groups:
                    profile.groups.append(group)
            hist_block = re.search(r'(?is)История\s+изменения\s+имени\s*:\s*(.*?)\s*👥\s*Группы\s*:', payload)
            if hist_block:
                for ln in re.split(r'\r?\n', hist_block.group(1)):
                    val = ln.strip('•- \t>')
                    if val and val not in profile.history:
                        profile.history.append(val)

        if bot_name == 'bot_b':
            bots_block = re.search(r'(?is)🤖\s*Bots\s*(.*)$', payload)
            if bots_block:
                for ln in re.split(r'\r?\n', bots_block.group(1)):
                    val = ln.strip('•- \t>')
                    if ':' in val and val not in profile.bot_data:
                        profile.bot_data.append(val)
