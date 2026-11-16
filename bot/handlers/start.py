from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.i18n import messages as translations
from bot.keyboards import main_menu

router = Router(name="start")


@router.message(Command("start"))
async def start(message: Message, repository, user_language: str = "kk") -> None:
    await repository.register_user(message.from_user.id)
    await message.answer(translations(user_language)["start"], reply_markup=main_menu(user_language))


@router.message(Command("menu"))
async def menu_command(message: Message, runtime, user_language: str = "kk") -> None:
    runtime.feedback_pending.pop(message.from_user.id, None)
    await message.answer(translations(user_language)["menu"], reply_markup=main_menu(user_language))


@router.callback_query(F.data == "menu:main")
async def menu_callback(callback: CallbackQuery, runtime, user_language: str = "kk") -> None:
    runtime.feedback_pending.pop(callback.from_user.id, None)
    await callback.message.answer(translations(user_language)["menu"], reply_markup=main_menu(user_language))
    await callback.answer()


@router.callback_query(F.data == "menu:help")
async def help_callback(callback: CallbackQuery, user_language: str = "kk") -> None:
    await callback.message.answer(translations(user_language)["help"], reply_markup=main_menu(user_language))
    await callback.answer()


@router.message(Command("help"))
async def help_command(message: Message, user_language: str = "kk") -> None:
    await message.answer(translations(user_language)["help"])


@router.message(Command("about"))
async def about(message: Message, user_language: str = "kk") -> None:
    await message.answer(translations(user_language)["about"])


@router.message(Command("emergency"))
async def emergency(message: Message, user_language: str = "kk") -> None:
    await message.answer(translations(user_language)["emergency"])


@router.message(Command("delete_my_data"))
async def delete_my_data(message: Message, repository, user_language: str = "kk") -> None:
    await repository.delete_user_data(message.from_user.id)
    await message.answer(translations(user_language)["delete_done"])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Қазақша", callback_data="lang:kk"),
            InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
        ]])


@router.message(Command("lang"))
async def language_command(message: Message, user_language: str = "kk") -> None:
    await message.answer(translations(user_language)["choose_language"], reply_markup=language_keyboard())


@router.callback_query(F.data == "menu:lang")
async def language_callback(callback: CallbackQuery, user_language: str = "kk") -> None:
    await callback.message.answer(translations(user_language)["choose_language"], reply_markup=language_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("lang:"))
async def change_language(callback: CallbackQuery, repository) -> None:
    language = callback.data.split(":")[1]
    if language not in {"kk", "ru"}:
        await callback.answer()
        return
    await repository.set_language(callback.from_user.id, language)
    await callback.message.answer(translations(language)["language_saved"], reply_markup=main_menu(language))
    await callback.answer()
