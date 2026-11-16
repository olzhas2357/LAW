from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class UserLanguageMiddleware(BaseMiddleware):
    def __init__(self, repository) -> None:
        self.repository = repository

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user:
            data["user_language"] = await self.repository.get_language(user.id)
        return await handler(event, data)
