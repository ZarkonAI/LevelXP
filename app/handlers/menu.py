import logging
from aiogram import Router, F
from aiogram.types import Message

from app.keyboards import main_menu_kb
from app import texts

log = logging.getLogger("handlers.menu")
router = Router()

MUSCLE_LABELS = {
    "legs": "🦵 Ноги",
    "back": "🧱 Спина",
    "chest": "🫀 Грудь",
    "shoulders": "🧍 Плечи",
    "arms": "💪 Руки",
    "core": "🎯 Кор",
}


def render_bar(value: int, max_value: int = 200, segments: int = 6) -> str:
    if max_value <= 0:
        max_value = 1
    ratio = min(max(value, 0) / max_value, 1)
    filled = round(ratio * segments)
    return "▰" * filled + "▱" * (segments - filled)


@router.message(F.text == "↩️ В меню")
async def back_to_menu(message: Message):
    await message.answer(texts.MENU, reply_markup=main_menu_kb())


@router.message(F.text == "🧬 Персонаж")
async def character(message: Message, db):
    try:
        tg_id = message.from_user.id
        user = db.get_or_create_user(tg_id, message.from_user.username)
        db.ensure_progress(user["id"])
        p = db.get_progress(user["id"])

        muscles = p.get("muscles") or {}
        lvl = p.get("level", 1)
        xp = p.get("xp", 0)
        xp_to_next = 100 + int(lvl) * 25

        text = (
            "<b>Персонаж</b>\n"
            f"Уровень: <b>{lvl}</b>\n"
            f"XP: <b>{xp}/{xp_to_next}</b>\n\n"
            "<b>Мышцы</b>\n"
            + "\n".join(muscle_lines)
        )
        await message.answer(text, reply_markup=main_menu_kb())
    except Exception:
        log.exception("character failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())

@router.message(F.text.in_({"📒 История", "🔁 Шаблоны", "⚙️ Настройки"}))
async def stub_sections(message: Message):
    await message.answer(
        "Этот раздел будет в следующих шагах спринта (D2–D4). Сейчас готовим каркас и БД.",
        reply_markup=main_menu_kb(),
    )
