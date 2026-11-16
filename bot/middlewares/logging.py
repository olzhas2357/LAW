import logging

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.services.safety import mask_pii

logger = logging.getLogger(__name__)


class SafeLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        message = getattr(event, "message", None)
        text = getattr(message, "text", None)
        if text:
            logger.info("Incoming Telegram message: %s", mask_pii(text)[:500])
        return await handler(event, data)
