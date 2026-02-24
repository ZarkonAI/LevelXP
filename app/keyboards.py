from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def _build_rows(buttons: list[str], row_width: int = 2) -> list[list[KeyboardButton]]:
    rows: list[list[KeyboardButton]] = []
    for idx in range(0, len(buttons), row_width):
        chunk = buttons[idx : idx + row_width]
        rows.append([KeyboardButton(text=text) for text in chunk])
    return rows



def _build_rows(buttons: list[str], row_width: int = 2) -> list[list[KeyboardButton]]:
    rows: list[list[KeyboardButton]] = []
    for idx in range(0, len(buttons), row_width):
        chunk = buttons[idx : idx + row_width]
        rows.append([KeyboardButton(text=text) for text in chunk])
    return rows


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏋️ Тренировка"), KeyboardButton(text="🧬 Персонаж")],
            [KeyboardButton(text="📒 История"), KeyboardButton(text="🔁 Шаблоны")],
            [KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери действие…",
    )


def back_to_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="↩️ В меню")]],
        resize_keyboard=True,
    )


def training_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚡ Быстрая запись")],
            [KeyboardButton(text="↩️ В меню")],
        ],
        resize_keyboard=True,
    )


def mode_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏋️ Силовая (одинаковый отдых)")],
            [KeyboardButton(text="🔁 Отдых по подходам")],
            [KeyboardButton(text="↩️ В меню")],
        ],
        resize_keyboard=True,
    )


def muscle_choice_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🦵 Ноги"), KeyboardButton(text="🧱 Спина")],
            [KeyboardButton(text="🫀 Грудь"), KeyboardButton(text="🧍 Плечи")],
            [KeyboardButton(text="💪 Руки"), KeyboardButton(text="🎯 Кор")],
            [KeyboardButton(text="↩️ Назад"), KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def back_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="↩️ Назад"), KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def confirm_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Сохранить"), KeyboardButton(text="✏️ Изменить")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def exercises_kb(exercises: list[dict]) -> ReplyKeyboardMarkup:
    names = [str(exercise.get("name", "")) for exercise in exercises if exercise.get("name")]
    keyboard = _build_rows(names, row_width=2)
    keyboard.append([KeyboardButton(text="➕ Своё упражнение")])
    keyboard.append([KeyboardButton(text="↩️ Назад"), KeyboardButton(text="❌ Отмена")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
