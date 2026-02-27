import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import texts
from app.db import ACHIEVEMENTS_META
from app.keyboards import main_menu_kb

log = logging.getLogger("handlers.achievements")
router = Router()

ACHIEVEMENTS_INFO = [
    ("first_workout", "Сделать 1 тренировку"),
    ("workouts_10", "Сделать 10 тренировок"),
    ("workouts_30", "Сделать 30 тренировок"),
    ("sets_100", "Набрать 100 подходов суммарно"),
    ("legs_100", "Прокачка ног 100+"),
    ("chest_100", "Прокачка груди 100+"),
    ("back_100", "Прокачка спины 100+"),
    ("streak_3", "3 дня подряд с выполненными тренировками"),
]


@router.message(F.text == "🏆 Достижения")
async def show_achievements(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.ensure_progress(user["id"])
        progress = db.get_progress(user["id"])

        raw = progress.get("achievements")
        unlocked = {str(item) for item in raw if isinstance(item, str)} if isinstance(raw, list) else set()

        lines = [texts.ACHIEVEMENTS_TITLE, ""]
        for achievement_id, condition in ACHIEVEMENTS_INFO:
            title = ACHIEVEMENTS_META.get(achievement_id, achievement_id)
            icon = "✅" if achievement_id in unlocked else "🔒"
            lines.append(f"{icon} {title} — {condition}")

        await message.answer("\n".join(lines), reply_markup=main_menu_kb())
    except Exception:
        log.exception("show_achievements failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
