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
    labels = translations(getattr(runtime, "language", "kk"))
    data = await runtime.repository.stats()
    positive = data["ratings"].get(1, 0)
    negative = data["ratings"].get(0, 0)
    total = data["total_questions"]
    ratio = (data["unanswered"] / total * 100) if total else 0
    text = (
        f"{labels['admin_users']}: {data['users']}\n"
        f"{labels['admin_daily_questions']}: {data['daily_questions']}\n"
        f"{labels['admin_unanswered_ratio']}: {ratio:.1f}%\n"
        f"👍 {positive} / 👎 {negative}\n"
        f"{labels['admin_llm_tokens']}: {data['daily_tokens']}\n"
        f"{labels['admin_llm_cost']}: ${data['daily_cost']:.4f}"
    )
    if data["top_records"]:
        topic_counts = Counter()
        for record_id, count in data["top_records"]:
            record = runtime.records_by_id.get(record_id)
            if record:
                topic_counts[record.topic] += count
        text += f"\n\n{labels['admin_top_topics']}\n" + "\n".join(
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
        caption=f"{translations(getattr(runtime, 'language', 'kk'))['admin_unanswered_caption']}: {len(rows)}",
    )


@router.message(Command("reload"))
async def reload_data(message: Message, runtime) -> None:
    if not is_admin(message.from_user.id, runtime):
        return
    await runtime.reload()
    await message.answer(translations(getattr(runtime, "language", "kk"))["refresh_done"])


@router.message(Command("broadcast"))
async def broadcast(message: Message, runtime) -> None:
    if not is_admin(message.from_user.id, runtime):
        return
    content = message.text.partition(" ")[2].strip()
    text = translations(getattr(runtime, "language", "kk"))
    if not content:
        await message.answer(text["admin_broadcast_usage"])
        return
    runtime.broadcast_pending[message.from_user.id] = content
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    await message.answer(
        text["admin_broadcast_confirm"] + "\n\n" + content[:1000],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=text["admin_confirm"], callback_data="broadcast:yes"),
            InlineKeyboardButton(text=text["admin_cancel"], callback_data="broadcast:no"),
        ]]),
    )


@router.callback_query(F.data.startswith("broadcast:"))
async def confirm_broadcast(callback: CallbackQuery, runtime) -> None:
    if not is_admin(callback.from_user.id, runtime):
        await callback.answer()
        return
    content = runtime.broadcast_pending.pop(callback.from_user.id, None)
    text = translations(getattr(runtime, "language", "kk"))
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
        await callback.message.answer(
            f"{text['admin_sent']}: {sent}; {text['admin_failed']}: {failed}"
        )
    else:
        await callback.message.answer(text["admin_broadcast_cancelled"])
    await callback.answer()
