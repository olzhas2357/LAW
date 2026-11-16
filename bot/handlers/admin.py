import csv
import io
from collections import Counter

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.i18n import messages as translations

router = Router(name="admin")


def is_admin(user_id: int, runtime) -> bool:
    return user_id in runtime.settings.admin_ids


@router.message(Command("stats"))
async def stats(message: Message, runtime) -> None:
    if not is_admin(message.from_user.id, runtime):
        return
    data = await runtime.repository.stats()
    positive = data["ratings"].get(1, 0)
    negative = data["ratings"].get(0, 0)
    total = data["total_questions"]
    ratio = (data["unanswered"] / total * 100) if total else 0
    text = (
        f"Пайдаланушылар: {data['users']}\n"
        f"Бүгінгі сұрақтар: {data['daily_questions']}\n"
        f"Жауапсыз үлесі: {ratio:.1f}%\n"
        f"👍 {positive} / 👎 {negative}\n"
        f"LLM токендері (бүгін): {data['daily_tokens']}\n"
        f"LLM шығыны (бүгін): ${data['daily_cost']:.4f}"
    )
    if data["top_records"]:
        topic_counts = Counter()
        for record_id, count in data["top_records"]:
            record = runtime.records_by_id.get(record_id)
            if record:
                topic_counts[record.topic] += count
        text += "\n\nЖиі тақырыптар:\n" + "\n".join(
            f"• {topic}: {count}" for topic, count in topic_counts.most_common(10)
        )
    await message.answer(text)


@router.message(Command("unanswered"))
async def unanswered(message: Message, runtime) -> None:
    if not is_admin(message.from_user.id, runtime):
        return
    rows = await runtime.repository.unanswered_rows()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "question", "created_at"])
    writer.writerows(rows)
    await message.answer_document(
        document=BufferedInputFile(buffer.getvalue().encode("utf-8-sig"), filename="unanswered.csv"),
        caption=f"Жауап табылмаған сұрақтар: {len(rows)}",
    )


@router.message(Command("reload"))
async def reload_data(message: Message, runtime) -> None:
    if not is_admin(message.from_user.id, runtime):
        return
    await runtime.reload()
    await message.answer(translations()["refresh_done"])


@router.message(Command("broadcast"))
async def broadcast(message: Message, runtime) -> None:
    if not is_admin(message.from_user.id, runtime):
        return
    content = message.text.partition(" ")[2].strip()
    if not content:
        await message.answer("Қолдану: /broadcast хабарлама мәтіні")
        return
    runtime.broadcast_pending[message.from_user.id] = content
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    await message.answer(
        "Хабарламаны барлық пайдаланушыға жіберуді растаңыз:\n\n" + content[:1000],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Растау", callback_data="broadcast:yes"),
            InlineKeyboardButton(text="Болдырмау", callback_data="broadcast:no"),
        ]]),
    )


@router.callback_query(F.data.startswith("broadcast:"))
async def confirm_broadcast(callback: CallbackQuery, runtime) -> None:
    if not is_admin(callback.from_user.id, runtime):
        await callback.answer()
        return
    content = runtime.broadcast_pending.pop(callback.from_user.id, None)
    if callback.data.endswith(":yes") and content:
        users = await runtime.repository.user_ids()
        sent = 0
        failed = 0
        for user_id in users:
            try:
                await callback.bot.send_message(user_id, content)
                sent += 1
            except Exception:
                runtime.logger.exception("Broadcast delivery failed for user %s", user_id)
                failed += 1
        await callback.message.answer(f"Жіберілді: {sent}; сәтсіз: {failed}")
    else:
        await callback.message.answer("Таратылым болдырылмады.")
    await callback.answer()
