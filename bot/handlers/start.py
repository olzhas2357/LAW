from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.i18n import messages as translations
from bot.keyboards import main_menu

router = Router(name="start")


@router.message(Command("start"))
async def start(message: Message, repository) -> None:
    await repository.register_user(message.from_user.id)
    await message.answer(translations()["start"], reply_markup=main_menu())


@router.message(Command("menu"))
async def menu_command(message: Message, runtime) -> None:
    runtime.feedback_pending.pop(message.from_user.id, None)
    await message.answer(translations()["menu"], reply_markup=main_menu())


@router.callback_query(F.data == "menu:main")
async def menu_callback(callback: CallbackQuery, runtime) -> None:
    runtime.feedback_pending.pop(callback.from_user.id, None)
    await callback.message.answer(translations()["menu"], reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "menu:help")
async def help_callback(callback: CallbackQuery) -> None:
    await callback.message.answer(translations()["help"], reply_markup=main_menu())
    await callback.answer()


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(translations()["help"])


@router.message(Command("about"))
async def about(message: Message) -> None:
    await message.answer(translations()["about"])


@router.message(Command("emergency"))
async def emergency(message: Message) -> None:
    await message.answer(translations()["emergency"])


@router.message(Command("delete_my_data"))
async def delete_my_data(message: Message, repository) -> None:
    await repository.delete_user_data(message.from_user.id)
    await message.answer(translations()["delete_done"])
