from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.i18n import SUPPORTED_LANGUAGES, messages as translations
from bot.keyboards import language_keyboard, main_menu

router = Router(name="start")


@router.message(Command("start"))
async def start(message: Message, repository, runtime) -> None:
    await repository.register_user(message.from_user.id)
    language = getattr(runtime, "language", "kk")
    await message.answer(translations(language)["start"], reply_markup=main_menu(language))


@router.message(Command("menu"))
async def menu_command(message: Message, runtime) -> None:
    runtime.feedback_pending.pop(message.from_user.id, None)
    language = getattr(runtime, "language", "kk")
    await message.answer(translations(language)["menu"], reply_markup=main_menu(language))


@router.callback_query(F.data == "menu:main")
async def menu_callback(callback: CallbackQuery, runtime) -> None:
    runtime.feedback_pending.pop(callback.from_user.id, None)
    language = getattr(runtime, "language", "kk")
    await callback.message.answer(translations(language)["menu"], reply_markup=main_menu(language))
    await callback.answer()


@router.callback_query(F.data == "menu:language")
async def language_menu(callback: CallbackQuery, runtime) -> None:
    language = getattr(runtime, "language", "kk")
    await callback.message.answer(
        translations(language)["choose_language"],
        reply_markup=language_keyboard(language),
    )
    await callback.answer()


@router.message(Command("language"))
async def language_command(message: Message, runtime) -> None:
    language = getattr(runtime, "language", "kk")
    await message.answer(
        translations(language)["choose_language"],
        reply_markup=language_keyboard(language),
    )


@router.callback_query(F.data.startswith("language:"))
async def select_language(callback: CallbackQuery, runtime) -> None:
    language = callback.data.split(":", 1)[1]
    if language not in SUPPORTED_LANGUAGES:
        current_language = getattr(runtime, "language", "kk")
        await callback.answer(
            translations(current_language)["unsupported_language"],
            show_alert=True,
        )
        return
    await runtime.repository.set_language(callback.from_user.id, language)
    runtime.topic_pages.pop(callback.from_user.id, None)
    runtime.feedback_pending.pop(callback.from_user.id, None)
    await callback.message.answer(
        translations(language)["language_changed"],
        reply_markup=main_menu(language),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:help")
async def help_callback(callback: CallbackQuery, runtime) -> None:
    language = getattr(runtime, "language", "kk")
    await callback.message.answer(translations(language)["help"], reply_markup=main_menu(language))
    await callback.answer()


@router.message(Command("help"))
async def help_command(message: Message, runtime) -> None:
    language = getattr(runtime, "language", "kk")
    await message.answer(translations(language)["help"])


@router.message(Command("about"))
async def about(message: Message, runtime) -> None:
    language = getattr(runtime, "language", "kk")
    await message.answer(translations(language)["about"])


@router.message(Command("emergency"))
async def emergency(message: Message, runtime) -> None:
    language = getattr(runtime, "language", "kk")
    await message.answer(translations(language)["emergency"])


@router.message(Command("delete_my_data"))
async def delete_my_data(message: Message, repository, runtime) -> None:
    await repository.delete_user_data(message.from_user.id)
    language = getattr(runtime, "language", "kk")
    await message.answer(translations(language)["delete_done"])
