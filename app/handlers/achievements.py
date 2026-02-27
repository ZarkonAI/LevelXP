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
async def show_achievements(message: Message, state: FSMContext):
    try:
        await state.clear()
        await message.answer("Скоро", reply_markup=main_menu_kb())
    except Exception:
        log.exception("show_achievements failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
