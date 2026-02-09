import asyncio
import re
from dataclasses import dataclass

from telethon import TelegramClient, events
from telethon.errors import ChatWriteForbiddenError, FloodWaitError, UserIsBlockedError
from telethon.tl.custom.message import Message

from models import RawBotResponses

BOT_A = '@Botfindinformation_bot'
BOT_B = '@WOW_MYAI_BOT'


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

    async def fetch_info(self, target: str) -> RawBotResponses:
        res_a, res_b = await asyncio.gather(
            self._query_botfind(target),
            self._query_wow(target),
        )
        return RawBotResponses(botfindinformation=res_a, wow_myai=res_b)

    async def _query_botfind(self, target: str) -> str:
        try:
            async with self.client.conversation(BOT_A, timeout=50) as conv:
                await conv.send_message(target)
                first = await conv.get_response()

                await self._click_telegram_button(first)
                final = await conv.get_response()
                return final.raw_text or first.raw_text or ''
        except asyncio.TimeoutError:
            return 'Timeout su Bot A.'
        except (UserIsBlockedError, ChatWriteForbiddenError):
            return 'Bot A bloccato o non scrivibile.'
        except FloodWaitError as exc:
            return f'Flood wait Bot A: {exc.seconds}s.'
        except Exception as exc:  # noqa: BLE001
            return f'Errore Bot A: {exc}'

    async def _click_telegram_button(self, message: Message) -> None:
        if not message.buttons:
            return

        for row in message.buttons:
            for button in row:
                if 'telegram' in (button.text or '').lower():
                    await message.click(text=button.text)
                    return

    async def _query_wow(self, target: str) -> str:
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

                self.client.add_event_handler(on_edited, events.MessageEdited(chats=entity))
                try:
                    await conv.get_response()
                    return await asyncio.wait_for(done_future, timeout=60)
                finally:
                    self.client.remove_event_handler(on_edited, events.MessageEdited)
        except asyncio.TimeoutError:
            return 'Timeout su Bot B.'
        except (UserIsBlockedError, ChatWriteForbiddenError):
            return 'Bot B bloccato o non scrivibile.'
        except FloodWaitError as exc:
            return f'Flood wait Bot B: {exc.seconds}s.'
        except Exception as exc:  # noqa: BLE001
            return f'Errore Bot B: {exc}'

    @staticmethod
    def _is_final_wow_text(text: str) -> bool:
        has_progress = re.search(r'\b\d{1,3}%\b', text)
        has_fields = any(k in text.lower() for k in ('id', 'nome', 'telefono', 'phone', 'registr'))
        return (not has_progress) and has_fields
