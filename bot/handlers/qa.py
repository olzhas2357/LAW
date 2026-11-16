import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.i18n import messages as translations
from bot.keyboards import matches_keyboard, rating_keyboard
from bot.services.formatter import format_answer, split_message
from bot.services.safety import (
    EMERGENCY_NUMBERS,
    EMERGENCY_NUMBERS_RU,
    SUPPORT_TEXT,
    SUPPORT_TEXT_RU,
    contains_sensitive_data,
    is_emergency,
    mask_pii,
)

logger = logging.getLogger(__name__)
router = Router(name="qa")


async def deliver_record(
    message,
    runtime,
    record,
    user_id: int,
    original_question: str | None = None,
    context_records=None,
) -> None:
    answer_text = record.answer
    if runtime.chat_provider and runtime.settings.use_llm:
        try:
            tokens, cost = await runtime.repository.usage_today()
            if tokens < runtime.settings.openai_daily_token_limit and cost < runtime.settings.openai_daily_cost_limit_usd:
                completion = await runtime.chat_provider.answer(
                    mask_pii(original_question or record.question),
                    (context_records or [record])[:3],
                )
                answer_text = completion.text
                await runtime.repository.record_usage(user_id, completion.tokens, completion.cost_usd)
        except Exception:
            logger.exception("LLM answer failed; returning dataset answer")
    text = format_answer(answer_text, record, runtime.disclaimer)
    for chunk in split_message(text):
        await message.answer(chunk, reply_markup=rating_keyboard(record.id, "kk"))


@router.message(F.text)
async def handle_question(message: Message, runtime, user_language: str = "kk") -> None:
    text = message.text.strip()
    if not text:
        return
    if len(text) > 4000:
        await message.answer(translations(user_language)["too_long"])
        return
    emergency = is_emergency(text)
    if emergency:
        numbers = EMERGENCY_NUMBERS_RU if user_language == "ru" else EMERGENCY_NUMBERS
        support = SUPPORT_TEXT_RU if user_language == "ru" else SUPPORT_TEXT
        await message.answer(f"{numbers}\n\n{support}")
    sensitive = contains_sensitive_data(text)
    safe_text = mask_pii(text)
    if sensitive:
        await message.answer(translations(user_language)["sensitive"])

    await runtime.repository.register_user(message.from_user.id)
    await message.bot.send_chat_action(message.chat.id, "typing")
    results = await runtime.search.search(safe_text, limit=runtime.settings.search_top_k)
    best = results[0] if results else None
    if best and best.score >= runtime.settings.search_high_threshold:
        await runtime.repository.log_question(message.from_user.id, safe_text, best.record.id, best.score)
        await deliver_record(
            message,
            runtime,
            best.record,
            message.from_user.id,
            safe_text,
            [result.record for result in results[:3]],
        )
        return
    if best and best.score >= runtime.settings.search_low_threshold:
        await runtime.repository.log_question(
            message.from_user.id,
            safe_text,
            None,
            best.score,
            track_unanswered=False,
        )
        await message.answer(
            translations(user_language)["ask"],
            reply_markup=matches_keyboard(results, user_language),
        )
        return
    await runtime.repository.log_question(message.from_user.id, safe_text, None, best.score if best else None)
    await message.answer(
        translations(user_language)["no_answer"] + f"\n\nℹ️ {runtime.disclaimer}",
        reply_markup=runtime.topic_menu(user_language),
    )


@router.callback_query(F.data.startswith("pick:"))
async def pick_match(callback: CallbackQuery, runtime) -> None:
    record_id = int(callback.data.split(":")[1])
    record = runtime.records_by_id.get(record_id)
    if record:
        await runtime.repository.log_question(callback.from_user.id, record.question, record.id, 1)
        await deliver_record(callback.message, runtime, record, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data.startswith("q:"))
async def pick_topic_question(callback: CallbackQuery, runtime) -> None:
    record_id = int(callback.data.split(":")[1])
    record = runtime.records_by_id.get(record_id)
    if record:
        await runtime.repository.log_question(callback.from_user.id, record.question, record.id, 1)
        await deliver_record(callback.message, runtime, record, callback.from_user.id)
    await callback.answer()


@router.message(F.voice)
async def voice_message(message: Message, runtime, user_language: str = "kk") -> None:
    if not runtime.settings.voice_enabled:
        await message.answer("Дауыстық хабарламаны тану әзірге өшірулі. Сұрағыңызды мәтінмен жіберіңіз.")
        return
    provider = runtime.embedding_provider
    if not hasattr(provider, "transcribe"):
        await message.answer("Дауысты тану провайдері конфигурацияланбаған. Сұрағыңызды мәтінмен жіберіңіз.")
        return
    try:
        import io

        if message.voice.file_size and message.voice.file_size > 10 * 1024 * 1024:
            await message.answer("Дауыстық файл тым үлкен. Қысқарақ хабарлама жіберіңіз.")
            return
        file_info = await message.bot.get_file(message.voice.file_id)
        audio = io.BytesIO()
        await message.bot.download_file(file_info.file_path, destination=audio)
        transcript = await provider.transcribe(audio.getvalue())
        await handle_question(
            message.model_copy(update={"text": transcript}),
            runtime,
            user_language,
        )
    except Exception:
        logger.exception("Voice transcription failed")
        await message.answer("Дауысты өңдеу мүмкін болмады. Сұрағыңызды мәтінмен жіберіңіз.")
