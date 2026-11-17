import logging
from collections.abc import Sequence

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.i18n import messages as translations
from bot.keyboards import matches_keyboard, rating_keyboard
from bot.services.data_loader import LegalRecord
from bot.services.formatter import format_answer, split_message
from bot.services.llm import InvalidChatCompletion
from bot.services.safety import (
    contains_sensitive_data,
    is_emergency,
    mask_pii,
)

logger = logging.getLogger(__name__)
router = Router(name="qa")


async def ai_answer(runtime, user_id: int, question: str, records: Sequence[LegalRecord]) -> str | None:
    if not runtime.settings.use_llm or runtime.chat_provider is None:
        return None
    try:
        tokens, cost = await runtime.repository.usage_today()
        if tokens >= runtime.settings.openai_daily_token_limit or cost >= runtime.settings.openai_daily_cost_limit_usd:
            logger.warning("Daily LLM usage limit reached")
            return None
        try:
            completion = await runtime.chat_provider.answer(mask_pii(question), records)
        except InvalidChatCompletion as exc:
            await runtime.repository.record_usage(user_id, exc.tokens, exc.cost_usd)
            raise
        await runtime.repository.record_usage(user_id, completion.tokens, completion.cost_usd)
        return completion.text
    except Exception:
        logger.exception("LLM answer failed")
        return None


async def send_answer(
    message,
    text: str,
    record_id: int | None,
    *,
    show_details: bool = False,
    language: str = "kk",
) -> None:
    chunks = split_message(text)
    for chunk in chunks[:-1]:
        await message.answer(chunk)
    if chunks:
        await message.answer(
            chunks[-1],
            reply_markup=rating_keyboard(
                record_id,
                show_details=show_details,
                language=language,
            ),
        )


async def deliver_record(
    message,
    runtime,
    record,
    user_id: int,
) -> None:
    language = getattr(runtime, "language", "kk")
    text = format_answer(record.answer, record, runtime.disclaimer, language)
    await send_answer(
        message, text, record.id,
        show_details=runtime.settings.use_llm and runtime.chat_provider is not None,
        language=language,
    )


@router.message(F.text)
async def handle_question(message: Message, runtime) -> None:
    language = getattr(runtime, "language", "kk")
    text = message.text.strip()
    if not text:
        return
    if len(text) > 4000:
        await message.answer(translations(language)["too_long"])
        return
    emergency = is_emergency(text)
    if emergency:
        await message.answer(
            f"{translations(language)['emergency']}\n\n"
            f"{translations(language)['emergency_support']}"
        )
    sensitive = contains_sensitive_data(text)
    safe_text = mask_pii(text)
    if sensitive:
        await message.answer(translations(language)["sensitive"])

    await runtime.repository.register_user(message.from_user.id)
    await message.bot.send_chat_action(message.chat.id, "typing")
    results = await runtime.search.search(safe_text, limit=runtime.settings.search_top_k)
    best = results[0] if results else None
    relevant = [result.record for result in results if result.score >= runtime.settings.search_low_threshold][:3]
    if relevant and runtime.settings.use_llm and runtime.chat_provider is not None:
        answer = await ai_answer(runtime, message.from_user.id, safe_text, relevant)
        if answer:
            await runtime.repository.log_question(
                message.from_user.id, safe_text, None, best.score, track_unanswered=False,
            )
            answer_text = translations(language)["ai_context"] + "\n\n" + answer
            sources = []
            for record in relevant:
                basis = "; ".join(record.legal_basis) or translations(language)["basis_not_specified"]
                sources.append(f"• {record.question}\n  {translations(language)['basis_label']}: {basis}")
            answer_text += "\n\n" + translations(language)["context_sources"] + "\n" + "\n".join(sources)
            if any(record.confidence == "check" for record in relevant):
                answer_text += "\n\n" + translations(language)["confidence_check"]
            await send_answer(
                message,
                format_answer(answer_text, disclaimer=runtime.disclaimer, language=language),
                None,
                language=language,
            )
            return
        await message.answer(translations(language)["ai_unavailable"])
    if best and best.score >= runtime.settings.search_high_threshold:
        await runtime.repository.log_question(message.from_user.id, safe_text, best.record.id, best.score)
        await deliver_record(
            message,
            runtime,
            best.record,
            message.from_user.id,
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
            translations(language)["ask"],
            reply_markup=matches_keyboard(results, language),
        )
        return
    await runtime.repository.log_question(message.from_user.id, safe_text, None, best.score if best else None)
    await message.answer(
        translations(language)["no_answer"] + f"\n\nℹ️ {runtime.disclaimer}",
        reply_markup=runtime.topic_menu(),
    )


@router.callback_query(F.data.startswith("detail:"))
async def explain_record(callback: CallbackQuery, runtime) -> None:
    language = getattr(runtime, "language", "kk")
    record_id = int(callback.data.split(":")[1])
    record = runtime.records_by_id.get(record_id)
    if record is None:
        await callback.answer(translations(language)["detail_missing"], show_alert=True)
        return
    await callback.answer()
    answer = await ai_answer(runtime, callback.from_user.id, record.question, [record])
    if answer is None:
        await callback.message.answer(translations(language)["ai_unavailable"])
        return
    text = translations(language)["ai_context"] + "\n\n" + answer
    await send_answer(
        callback.message,
        format_answer(text, record, runtime.disclaimer, language),
        record.id,
        language=language,
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
async def voice_message(message: Message, runtime) -> None:
    language = getattr(runtime, "language", "kk")
    if not runtime.settings.voice_enabled:
        await message.answer(translations(language)["voice_disabled"])
        return
    provider = runtime.embedding_provider
    if not hasattr(provider, "transcribe"):
        await message.answer(translations(language)["voice_unavailable"])
        return
    try:
        import io

        if message.voice.file_size and message.voice.file_size > 10 * 1024 * 1024:
            await message.answer(translations(language)["voice_too_large"])
            return
        file_info = await message.bot.get_file(message.voice.file_id)
        audio = io.BytesIO()
        await message.bot.download_file(file_info.file_path, destination=audio)
        transcript = await provider.transcribe(audio.getvalue())
        await handle_question(
            message.model_copy(update={"text": transcript}),
            runtime,
        )
    except Exception:
        logger.exception("Voice transcription failed")
        await message.answer(translations(language)["voice_failed"])
