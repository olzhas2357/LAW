from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.i18n import messages as translations

router = Router(name="feedback")


@router.message(Command("feedback"))
async def feedback_command(message: Message, runtime, user_language: str = "kk") -> None:
    runtime.feedback_pending[message.from_user.id] = None
    await message.answer(translations(user_language)["feedback"])


@router.callback_query(F.data.startswith("rate:"))
async def rate_answer(callback: CallbackQuery, runtime, user_language: str = "kk") -> None:
    _, value, record_id = callback.data.split(":")
    rating = int(value)
    if rating == 0:
        runtime.feedback_pending[callback.from_user.id] = int(record_id) or None
        await callback.message.answer(translations(user_language)["feedback_reason"])
    else:
        await runtime.repository.add_feedback(
            callback.from_user.id,
            int(record_id) or None,
            rating,
        )
        await callback.message.answer(translations(user_language)["thanks"])
    await callback.answer()


@router.message(F.text, lambda message, runtime: message.from_user.id in runtime.feedback_pending)
async def feedback_reason(message: Message, runtime, user_language: str = "kk") -> None:
    record_id = runtime.feedback_pending.pop(message.from_user.id, None)
    await runtime.repository.add_feedback(message.from_user.id, record_id, 0, message.text)
    await message.answer(translations(user_language)["thanks"])
