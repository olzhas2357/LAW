from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(language: str = "kk") -> InlineKeyboardMarkup:
    labels = ("📚 Тақырыптар", "🚨 Шұғыл көмек") if language == "kk" else ("📚 Темы", "🚨 Экстренная помощь")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=labels[0], callback_data="topics:0")],
        [InlineKeyboardButton(text=labels[1], callback_data="emergency")],
    ])


def topics_keyboard(topics: list[str], page: int, language: str) -> InlineKeyboardMarkup:
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
    return InlineKeyboardMarkup(inline_keyboard=rows)


def question_keyboard(records, page: int, language: str) -> InlineKeyboardMarkup:
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
    return InlineKeyboardMarkup(inline_keyboard=rows)


def matches_keyboard(results, language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{index}. {result.record.question[:70]}",
            callback_data=f"pick:{result.record.id}",
        )]
        for index, result in enumerate(results[:3], start=1)
    ])


def rating_keyboard(record_id: int | None, language: str) -> InlineKeyboardMarkup:
    rid = record_id or 0
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👍", callback_data=f"rate:1:{rid}"),
        InlineKeyboardButton(text="👎", callback_data=f"rate:0:{rid}"),
    ]])
