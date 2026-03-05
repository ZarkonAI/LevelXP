from datetime import datetime
import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def _build_rows(buttons: list[str], row_width: int = 2) -> list[list[KeyboardButton]]:
    rows: list[list[KeyboardButton]] = []
    for idx in range(0, len(buttons), row_width):
        chunk = buttons[idx : idx + row_width]
        rows.append([KeyboardButton(text=text) for text in chunk])
    return rows




def _strip_tech_id(text: str) -> str:
    return re.sub(r"\s*\(#\d+\)", "", text or "").strip()

def _format_date(raw_date: str | None) -> str:
    if not raw_date:
        return "--.--.----"
    try:
        return datetime.fromisoformat(raw_date).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(raw_date)


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏋️ Тренировка"), KeyboardButton(text="🧬 Персонаж")],
            [KeyboardButton(text="📒 История"), KeyboardButton(text="🔁 Шаблоны")],
            [KeyboardButton(text="🏆 Достижения"), KeyboardButton(text="⚙️ Настройки")],
            [KeyboardButton(text="❓ Помощь")],
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
    keyboard.append([KeyboardButton(text="🔎 Поиск"), KeyboardButton(text="➕ Своё упражнение")])
    keyboard.append([KeyboardButton(text="↩️ Назад"), KeyboardButton(text="❌ Отмена")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def history_list_kb(workouts: list[dict]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for idx, workout in enumerate(workouts[:10], start=1):
        title = _strip_tech_id(str(workout.get("title") or "Тренировка"))
        workout_date = _format_date(workout.get("workout_date"))
        rows.append([KeyboardButton(text=f"{idx}) {workout_date} · {title}")])
    rows.append([KeyboardButton(text="↩️ В меню")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def history_action_kb(status: str | None) -> ReplyKeyboardMarkup:
    status_button = "✅ Отметить выполненной" if status != "done" else "☑️ Снять отметку"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔁 Повторить")],
            [KeyboardButton(text="✏️ Исправить")],
            [KeyboardButton(text=status_button)],
            [KeyboardButton(text="💾 Сохранить как шаблон")],
            [KeyboardButton(text="↩️ Назад")],
            [KeyboardButton(text="↩️ В меню")],
        ],
        resize_keyboard=True,
    )


def confirm_edit_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Сохранить правки")],
            [KeyboardButton(text="❌ Отмена")],
            [KeyboardButton(text="↩️ Назад")],
        ],
        resize_keyboard=True,
    )


def edit_confirm_kb() -> ReplyKeyboardMarkup:
    return confirm_edit_kb()


def templates_list_kb(templates: list[dict]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for idx, template in enumerate(templates, start=1):
        rows.append([KeyboardButton(text=f"{idx}) {template.get('name', 'Template')}")])
    rows.append([KeyboardButton(text="↩️ В меню")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def templates_confirm_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Применить")],
            [KeyboardButton(text="✏️ Изменить перед применением")],
            [KeyboardButton(text="↩️ Назад")],
            [KeyboardButton(text="↩️ В меню")],
        ],
        resize_keyboard=True,
    )


def back_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="↩️ Назад")],
            [KeyboardButton(text="↩️ В меню")],
        ],
        resize_keyboard=True,
    )


def repeat_options_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Точно так же")],
            [KeyboardButton(text="✏️ Изменить перед записью")],
            [KeyboardButton(text="↩️ Назад")],
            [KeyboardButton(text="↩️ В меню")],
        ],
        resize_keyboard=True,
    )


def settings_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚖️ Единицы")],
            [KeyboardButton(text="🕒 Часовой пояс")],
            [KeyboardButton(text="🧾 Режим интерфейса")],
            [KeyboardButton(text="↩️ В меню")],
        ],
        resize_keyboard=True,
    )


def units_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="kg"), KeyboardButton(text="lb")],
            [KeyboardButton(text="↩️ Назад"), KeyboardButton(text="↩️ В меню")],
        ],
        resize_keyboard=True,
    )


def ui_mode_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Полный"), KeyboardButton(text="Компактный")],
            [KeyboardButton(text="↩️ Назад"), KeyboardButton(text="↩️ В меню")],
        ],
        resize_keyboard=True,
    )


def history_list_inline_kb(workouts: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, workout in enumerate(workouts[:10], start=1):
        title = _strip_tech_id(str(workout.get("title") or "Тренировка"))
        workout_date = _format_date(workout.get("workout_date"))
        rows.append([InlineKeyboardButton(text=f"{idx}) {workout_date} · {title}", callback_data=f"history:open:{workout.get('id')}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_action_inline_kb(workout_id: int, status: str | None) -> InlineKeyboardMarkup:
    status_button = "✅ Статус" if status != "done" else "☑️ Статус"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Повторить", callback_data=f"history:repeat:{workout_id}")],
            [InlineKeyboardButton(text="✏️ Исправить", callback_data=f"history:edit:{workout_id}")],
            [InlineKeyboardButton(text=status_button, callback_data=f"history:status:{workout_id}")],
            [InlineKeyboardButton(text="💾 Шаблон", callback_data=f"history:template:{workout_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="history:back")],
        ]
    )


def templates_list_inline_kb(templates: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for row in templates:
        t_id = int(row.get("id"))
        rows.append([InlineKeyboardButton(text=str(row.get("name") or "Template"), callback_data=f"templates:open:{t_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def templates_confirm_inline_kb(template_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Применить", callback_data=f"templates:apply:{template_id}")],
            [InlineKeyboardButton(text="✏️ Изменить перед применением", callback_data=f"templates:edit:{template_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="templates:back")],
        ]
    )
