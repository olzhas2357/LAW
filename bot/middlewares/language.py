from aiogram import BaseMiddleware

from bot.i18n import normalize_language


class LanguageMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        runtime = data["runtime"]
        language = await runtime.repository.get_language(user.id)
        if language is None:
            language = normalize_language(user.language_code)
            await runtime.repository.set_language(user.id, language)
        data["runtime"] = runtime.for_language(language)
        return await handler(event, data)
