import time
from collections import defaultdict, deque

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.config import Settings


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings) -> None:
        self.limit = settings.throttle_messages_per_minute
        self.events: dict[int, deque[float]] = defaultdict(deque)

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        now = time.monotonic()
        events = self.events[user.id]
        while events and now - events[0] >= 60:
            events.popleft()
        if len(events) >= self.limit:
            message = getattr(event, "message", None)
            if message:
                await message.answer("Сұраулар тым жиі жіберілді. Бір минуттан кейін қайталап көріңіз.")
            return None
        events.append(now)
        return await handler(event, data)
