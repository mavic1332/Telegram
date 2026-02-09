import asyncio
from dataclasses import dataclass
from typing import Dict

from telethon import TelegramClient
from telethon.errors import ChatWriteForbiddenError, FloodWaitError, UserIsBlockedError

SOURCE_BOTS = ('@Botfindinformation_bot', '@WOW_MYAI_BOT')


@dataclass
class ResolverClient:
    api_id: int
    api_hash: str
    phone_number: str
    session_name: str = 'test1_resolver'

    def __post_init__(self) -> None:
        self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)

    async def start(self) -> None:
        await self.client.start(phone=self.phone_number)

    async def stop(self) -> None:
        await self.client.disconnect()

    async def _query_one(self, bot_username: str, target: str) -> str:
        try:
            async with self.client.conversation(bot_username, timeout=45) as conv:
                await conv.send_message(target)
                reply = await conv.get_response()
                return reply.raw_text or ''
        except asyncio.TimeoutError:
            return f'⚠️ {bot_username}: timeout di risposta.'
        except (UserIsBlockedError, ChatWriteForbiddenError):
            return f'⚠️ {bot_username}: bot bloccato o non raggiungibile.'
        except FloodWaitError as exc:
            return f'⚠️ {bot_username}: flood wait {exc.seconds}s.'
        except Exception as exc:  # noqa: BLE001
            return f'⚠️ {bot_username}: errore inatteso ({exc}).'

    async def fetch_info(self, target: str) -> Dict[str, str]:
        responses = await asyncio.gather(*(self._query_one(bot, target) for bot in SOURCE_BOTS))
        return {bot: text for bot, text in zip(SOURCE_BOTS, responses, strict=True)}
