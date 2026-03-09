from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MUSCLE_BUTTONS = [
    ("🦵 Ноги", "legs"),
    ("🧱 Спина", "back"),
    ("🫀 Грудь", "chest"),
    ("🧍 Плечи", "shoulders"),
    ("💪 Руки", "arms"),
    ("🎯 Кор", "core"),
]


def training_start_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Быстрая запись", callback_data="quick:start")],
            [InlineKeyboardButton(text="↩️ В меню", callback_data="menu:back")],
        ]
    )


def mode_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏋️ Силовая", callback_data="mode:strength")],
            [InlineKeyboardButton(text="🔁 Отдых по подходам", callback_data="mode:pattern")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:start")],
            [InlineKeyboardButton(text="↩️ В меню", callback_data="menu:back")],
        ]
    )


def category_inline_kb() -> InlineKeyboardMarkup:
    keyboard = []
    for idx in range(0, len(MUSCLE_BUTTONS), 2):
        chunk = MUSCLE_BUTTONS[idx : idx + 2]
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"cat:{value}") for label, value in chunk])
    keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="search:open")])
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back:mode"),
        InlineKeyboardButton(text="↩️ В меню", callback_data="menu:back"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def exercises_inline_kb(exercises: list[dict], page: int, has_next: bool) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for exercise in exercises:
        exercise_id = int(exercise.get("id") or 0)
        if exercise_id <= 0:
            continue
        label = str(exercise.get("display_name") or exercise.get("name") or "Упражнение")
        keyboard.append([InlineKeyboardButton(text=label[:64], callback_data=f"ex:{exercise_id}")])

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"page:{page - 1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"page:{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="search:open")])
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back:cat"),
        InlineKeyboardButton(text="↩️ В меню", callback_data="menu:back"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def search_prompt_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:search")],
            [InlineKeyboardButton(text="↩️ В меню", callback_data="menu:back")],
        ]
    )


def search_results_inline_kb(exercises: list[dict], page: int, has_next: bool) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for exercise in exercises:
        exercise_id = int(exercise.get("id") or 0)
        if exercise_id <= 0:
            continue
        label = str(exercise.get("display_name") or exercise.get("name") or "Упражнение")
        keyboard.append([InlineKeyboardButton(text=label[:64], callback_data=f"ex:{exercise_id}")])

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"search_page:{page - 1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"search_page:{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton(text="Сбросить поиск", callback_data="search:reset")])
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back:search"),
        InlineKeyboardButton(text="↩️ В меню", callback_data="menu:back"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
