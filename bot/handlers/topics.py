from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.i18n import messages as translations
from bot.keyboards import question_keyboard, topics_keyboard

router = Router(name="topics")


@router.message(Command("topics"))
async def show_topics(message: Message, runtime, user_language: str = "kk") -> None:
    await message.answer(
        translations(user_language)["topics"],
        reply_markup=topics_keyboard(runtime.dataset.topics, 0, user_language),
    )


@router.callback_query(F.data.startswith("topics:"))
async def topics_page(callback: CallbackQuery, runtime, user_language: str = "kk") -> None:
    page = max(0, int(callback.data.split(":")[1]))
    await callback.message.edit_reply_markup(
        reply_markup=topics_keyboard(runtime.dataset.topics, page, user_language)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("topic:"))
async def topic_questions(callback: CallbackQuery, runtime, user_language: str = "kk") -> None:
    index = int(callback.data.split(":")[1])
    if index >= len(runtime.dataset.topics):
        await callback.answer()
        return
    topic = runtime.dataset.topics[index]
    runtime.topic_pages[callback.from_user.id] = topic
    records = runtime.records_by_topic[topic]
    await callback.message.edit_text(topic, reply_markup=question_keyboard(records, 0, user_language))
    await callback.answer()


@router.callback_query(F.data.startswith("qs:"))
async def question_page(callback: CallbackQuery, runtime, user_language: str = "kk") -> None:
    page = max(0, int(callback.data.split(":")[1]))
    topic = runtime.topic_pages.get(callback.from_user.id)
    if topic not in runtime.records_by_topic:
        await callback.answer()
        return
    await callback.message.edit_reply_markup(
        reply_markup=question_keyboard(runtime.records_by_topic[topic], page, user_language)
    )
    await callback.answer()


@router.callback_query(F.data == "emergency")
async def emergency_button(callback: CallbackQuery, user_language: str = "kk") -> None:
    await callback.message.answer(translations(user_language)["emergency"])
    await callback.answer()
