from aiogram import Router
from aiogram.types import InlineQuery, InputTextMessageContent, InlineQueryResultArticle

from bot.services.formatter import format_answer

router = Router(name="inline")


@router.inline_query()
async def inline_search(query: InlineQuery, runtime) -> None:
    language = getattr(runtime, "language", "kk")
    results = await runtime.search.search(query.query, limit=5)
    articles = [
        InlineQueryResultArticle(
            id=str(result.record.id),
            title=result.record.question[:128],
            description=result.record.answer[:200],
            input_message_content=InputTextMessageContent(
                message_text=format_answer(
                    result.record.answer,
                    result.record,
                    runtime.disclaimer,
                    language,
                )
            ),
        )
        for result in results
        if result.score >= runtime.settings.search_low_threshold
    ]
    await query.answer(articles, cache_time=15, is_personal=True)
