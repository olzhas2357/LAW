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


@router.message(Command("lang"))
async def language_command(message: Message, user_language: str = "kk") -> None:
    await message.answer(
        translations(user_language)["choose_language"],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Қазақша", callback_data="lang:kk"),
            InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
        ]]),
    )


@router.callback_query(F.data.startswith("lang:"))
async def change_language(callback: CallbackQuery, repository) -> None:
    language = callback.data.split(":")[1]
    if language not in {"kk", "ru"}:
        await callback.answer()
        return
    await repository.set_language(callback.from_user.id, language)
    await callback.message.answer(translations(language)["language_saved"])
    await callback.answer()
