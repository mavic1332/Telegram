import asyncio
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Tuple

from telethon import TelegramClient, events
from telethon.errors import ChatWriteForbiddenError, FloodWaitError, UserIsBlockedError

from models import RawBotResponses

BOT_A = '@Botfindinformation_bot'
BOT_B = '@WOW_MYAI_BOT'
BOT_A_ID = 8585975791
MAX_BOT_WAIT_S = 180
WAIT_UNTIL_RE = re.compile(r'new\s+requests\s+will\s+be\s+granted\s+at\s*(\d{1,2}:\d{2})', re.IGNORECASE)
COUNTDOWN_RE = re.compile(r'\b(\d{2}:\d{2})\b')
ProgressCb = Optional[Callable[[str], Awaitable[None]]]


@dataclass
class ResolverClient:
    api_id: int
    api_hash: str
    phone: str
    session_name: str = 'test1_resolver'

    def __post_init__(self) -> None:
        self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)

    async def start(self) -> None:
        await self.client.start(phone=self.phone)

    async def stop(self) -> None:
        await self.client.disconnect()

    async def fetch_info(self, target: str, mode: str = 'all', progress_cb: ProgressCb = None) -> RawBotResponses:
        if mode == 'bot_a':
            text_a, wait_a, retry_after, sec_a = await self._query_botfind(target)
            if progress_cb:
                await progress_cb('bot_a')
            return RawBotResponses(botfindinformation=text_a, bot_a_wait_until=wait_a, bot_a_retry_after=retry_after, bot_a_seconds=sec_a)

        if mode == 'bot_b':
            text_b, sec_b = await self._query_wow(target)
            if progress_cb:
                await progress_cb('bot_b')
            return RawBotResponses(wow_myai=text_b, bot_b_seconds=sec_b)

        task_a = asyncio.create_task(self._query_botfind(target))
        task_b = asyncio.create_task(self._query_wow(target))

        text_a, wait_a, retry_after, sec_a = ('Timeout su Bot A.', None, None, None)
        text_b, sec_b = ('Timeout su Bot B.', None)

        pending = {task_a, task_b}
        while pending:
            done, pending = await asyncio.wait(pending, timeout=MAX_BOT_WAIT_S, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                break
            for completed in done:
                try:
                    result = completed.result()
                except Exception:
                    continue

                if completed is task_a:
                    text_a, wait_a, retry_after, sec_a = result
                    if progress_cb:
                        await progress_cb('bot_a')
                elif completed is task_b:
                    text_b, sec_b = result
                    if progress_cb:
                        await progress_cb('bot_b')

            if task_a.done() and task_b.done():
                break

        for task in (task_a, task_b):
            if not task.done():
                task.cancel()

        return RawBotResponses(
            botfindinformation=text_a,
            wow_myai=text_b,
            bot_a_wait_until=wait_a,
            bot_a_retry_after=retry_after,
            bot_a_seconds=sec_a,
            bot_b_seconds=sec_b,
        )

    async def _listen_first_text(self, chat_id: int, timeout: int) -> Tuple[str, float]:
        loop = asyncio.get_running_loop()
        start = time.perf_counter()
        done_future: asyncio.Future[Tuple[str, float]] = loop.create_future()

        async def on_new_message(event: events.NewMessage.Event) -> None:
            text = (event.raw_text or '').strip()
            if text and not done_future.done():
                done_future.set_result((text, time.perf_counter() - start))

        event_filter = events.NewMessage(chats=[chat_id])
        self.client.add_event_handler(on_new_message, event_filter)
        try:
            return await asyncio.wait_for(done_future, timeout=timeout)
        finally:
            self.client.remove_event_handler(on_new_message, event_filter)

    async def _query_botfind(self, target: str) -> Tuple[str, Optional[str], Optional[str], float]:
        started = time.perf_counter()
        try:
            await self.client.send_message(BOT_A, target)
            text, sec_a = await self._listen_first_text(BOT_A_ID, MAX_BOT_WAIT_S)

            wait_until = self._extract_wait_time(text)
            retry_after = self._extract_countdown(text)
            parsed = self._apply_regex_enrichment('a', text)

            if wait_until or retry_after:
                return '', wait_until, retry_after, sec_a
            return parsed, None, None, sec_a
        except asyncio.TimeoutError:
            return 'Timeout su Bot A.', None, None, time.perf_counter() - started
        except (UserIsBlockedError, ChatWriteForbiddenError):
            return 'Bot A bloccato o non scrivibile.', None, None, time.perf_counter() - started
        except FloodWaitError as exc:
            return f'Flood wait Bot A: {exc.seconds}s.', None, None, time.perf_counter() - started
        except Exception as exc:  # noqa: BLE001
            return f'Errore Bot A: {exc}', None, None, time.perf_counter() - started

    async def _query_wow(self, target: str) -> Tuple[str, float]:
        started = time.perf_counter()
        try:
            entity = await self.client.get_entity(BOT_B)
            bot_b_id = entity.id
            await self.client.send_message(entity, target)
            text, sec_b = await self._listen_first_text(bot_b_id, MAX_BOT_WAIT_S)
            parsed = self._apply_regex_enrichment('b', text)
            return parsed, sec_b
        except asyncio.TimeoutError:
            return 'Timeout su Bot B.', time.perf_counter() - started
        except (UserIsBlockedError, ChatWriteForbiddenError):
            return 'Bot B bloccato o non scrivibile.', time.perf_counter() - started
        except FloodWaitError as exc:
            return f'Flood wait Bot B: {exc.seconds}s.', time.perf_counter() - started
        except Exception as exc:  # noqa: BLE001
            return f'Errore Bot B: {exc}', time.perf_counter() - started

    @staticmethod
    def _extract_wait_time(text: str) -> Optional[str]:
        match = WAIT_UNTIL_RE.search(text or '')
        return match.group(1) if match else None

    @staticmethod
    def _extract_countdown(text: str) -> Optional[str]:
        match = COUNTDOWN_RE.search(text or '')
        return match.group(1) if match else None

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
            if parts:
                return '\n'.join(parts) + '\n' + payload
            return payload

        found_search = re.search(r'(?im)^\s*Search\s+by\s+Telegram\s+ID\s+.*?(\d+)\s*$', payload)
        found_registered = re.search(r'(?is)Registered\s*\n\s*([^\n\r]+)', payload)
        parts = []
        if found_search:
            parts.append(f'Search by Telegram ID {found_search.group(1)}')
        if found_registered:
            parts.append('Registered')
            parts.append(found_registered.group(1).strip())
        if parts:
            return '\n'.join(parts) + '\n' + payload
        return payload
