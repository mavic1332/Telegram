import asyncio
import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from telethon import TelegramClient, events
from telethon.errors import ChatWriteForbiddenError, FloodWaitError, UserIsBlockedError
from telethon.tl.custom.message import Message

from models import RawBotResponses

BOT_A = '@Botfindinformation_bot'
BOT_B = '@WOW_MYAI_BOT'
WAIT_UNTIL_RE = re.compile(r'new\s+requests\s+will\s+be\s+granted\s+at\s*(\d{1,2}:\d{2})', re.IGNORECASE)
COUNTDOWN_RE = re.compile(r'\b(\d{2}:\d{2})\b')


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

    async def fetch_info(self, target: str, mode: str = 'all') -> RawBotResponses:
        if mode == 'bot_a':
            text_a, wait_a, retry_after, sec_a = await self._query_botfind(target)
            return RawBotResponses(
                botfindinformation=text_a,
                bot_a_wait_until=wait_a,
                bot_a_retry_after=retry_after,
                bot_a_seconds=sec_a,
            )
        if mode == 'bot_b':
            text_b, sec_b = await self._query_wow(target)
            return RawBotResponses(wow_myai=text_b, bot_b_seconds=sec_b)

        (text_a, wait_a, retry_after, sec_a), (text_b, sec_b) = await asyncio.gather(
            self._query_botfind(target),
            self._query_wow(target),
        )
        return RawBotResponses(
            botfindinformation=text_a,
            wow_myai=text_b,
            bot_a_wait_until=wait_a,
            bot_a_retry_after=retry_after,
            bot_a_seconds=sec_a,
            bot_b_seconds=sec_b,
        )

    async def _query_botfind(self, target: str) -> Tuple[str, Optional[str], Optional[str], float]:
        started = time.perf_counter()
        try:
            async with self.client.conversation(BOT_A, timeout=50) as conv:
                await conv.send_message(target)
                first = await conv.get_response()
                first_text = first.raw_text or ''

                wait_until = self._extract_wait_time(first_text)
                retry_after = self._extract_countdown(first_text)
                if wait_until or retry_after:
                    return '', wait_until, retry_after, time.perf_counter() - started

                await self._click_telegram_button(first)
                final = await conv.get_response()
                final_text = final.raw_text or first_text
                wait_until = self._extract_wait_time(final_text)
                retry_after = self._extract_countdown(final_text)
                if wait_until or retry_after:
                    return '', wait_until, retry_after, time.perf_counter() - started
                return final_text, None, None, time.perf_counter() - started
        except asyncio.TimeoutError:
            return 'Timeout su Bot A.', None, None, time.perf_counter() - started
        except (UserIsBlockedError, ChatWriteForbiddenError):
            return 'Bot A bloccato o non scrivibile.', None, None, time.perf_counter() - started
        except FloodWaitError as exc:
            return f'Flood wait Bot A: {exc.seconds}s.', None, None, time.perf_counter() - started
        except Exception as exc:  # noqa: BLE001
            return f'Errore Bot A: {exc}', None, None, time.perf_counter() - started

    @staticmethod
    def _extract_wait_time(text: str) -> Optional[str]:
        match = WAIT_UNTIL_RE.search(text or '')
        return match.group(1) if match else None

    @staticmethod
    def _extract_countdown(text: str) -> Optional[str]:
        match = COUNTDOWN_RE.search(text or '')
        return match.group(1) if match else None

    async def _click_telegram_button(self, message: Message) -> None:
        if not message.buttons:
            return
        for row in message.buttons:
            for button in row:
                if 'telegram' in (button.text or '').lower():
                    await message.click(text=button.text)
                    return

    async def _query_wow(self, target: str) -> Tuple[str, float]:
        started = time.perf_counter()
        loop = asyncio.get_running_loop()
        done_future: asyncio.Future[str] = loop.create_future()

        try:
            entity = await self.client.get_entity(BOT_B)
            async with self.client.conversation(entity, timeout=60) as conv:
                await conv.send_message(target)

                def on_edited(event: events.MessageEdited.Event) -> None:
                    text = (event.raw_text or '').strip()
                    if text and self._is_final_wow_text(text) and not done_future.done():
                        done_future.set_result(text)

                event_filter = events.MessageEdited(chats=entity)
                self.client.add_event_handler(on_edited, event_filter)
                try:
                    await conv.get_response()
                    result = await asyncio.wait_for(done_future, timeout=60)
                    return result, time.perf_counter() - started
                finally:
                    self.client.remove_event_handler(on_edited, event_filter)
        except asyncio.TimeoutError:
            return 'Timeout su Bot B.', time.perf_counter() - started
        except (UserIsBlockedError, ChatWriteForbiddenError):
            return 'Bot B bloccato o non scrivibile.', time.perf_counter() - started
        except FloodWaitError as exc:
            return f'Flood wait Bot B: {exc.seconds}s.', time.perf_counter() - started
        except Exception as exc:  # noqa: BLE001
            return f'Errore Bot B: {exc}', time.perf_counter() - started

    @staticmethod
    def _is_final_wow_text(text: str) -> bool:
        has_progress = re.search(r'\b\d{1,3}%\b', text)
        has_fields = any(k in text.lower() for k in ('id', 'nome', 'telefono', 'phone', 'registr', 'registered'))
        return (not has_progress) and has_fields
