from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import messages as translations


def menu_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text=translations()["menu_button"], callback_data="menu:main")


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Тақырыптар", callback_data="topics:0")],
        [InlineKeyboardButton(text="🚨 Шұғыл көмек", callback_data="emergency")],
        [
            InlineKeyboardButton(text=translations()["help_button"], callback_data="menu:help"),
        ],
    ])


def topics_keyboard(topics: list[str], page: int) -> InlineKeyboardMarkup:
    page_size = 8
    start = page * page_size
    rows = [
        [InlineKeyboardButton(text=topic, callback_data=f"topic:{topics.index(topic)}")]
        for topic in topics[start:start + page_size]
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"topics:{page - 1}"))
    if start + page_size < len(topics):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"topics:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([menu_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def question_keyboard(records, page: int) -> InlineKeyboardMarkup:
    page_size = 8
    start = page * page_size
    rows = [
        [InlineKeyboardButton(text=record.question[:90], callback_data=f"q:{record.id}")]
        for record in records[start:start + page_size]
    ]
    nav = []
    if page:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"qs:{page - 1}"))
    if start + page_size < len(records):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"qs:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(
        text=translations()["back_to_topics"],
        callback_data="topics:0",
    )])
    rows.append([menu_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def matches_keyboard(results) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{index}. {result.record.question[:70]}",
            callback_data=f"pick:{result.record.id}",
        )]
        for index, result in enumerate(results[:3], start=1)
    ]
    rows.append([menu_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rating_keyboard(record_id: int | None) -> InlineKeyboardMarkup:
    rid = record_id or 0
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍", callback_data=f"rate:1:{rid}"),
            InlineKeyboardButton(text="👎", callback_data=f"rate:0:{rid}"),
        ],
        [menu_button()],
    ])
