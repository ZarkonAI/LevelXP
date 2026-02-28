import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import texts
from app.keyboards import main_menu_kb

log = logging.getLogger("handlers.menu")
router = Router()


def render_bar(value: int, max_value: int = 200, segments: int = 6) -> str:
    try:
        v = max(0, int(value))
    except Exception:
        v = 0
    filled = int(round(min(v, max_value) / max_value * segments))
    filled = max(0, min(segments, filled))
    return "▰" * filled + "▱" * (segments - filled)


@router.message(Command("menu"))
async def menu_cmd(message: Message, state: FSMContext):
    try:
        await state.clear()
        await message.answer(texts.MENU, reply_markup=main_menu_kb())
    except Exception:
        log.exception("menu_cmd failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "❌ Отмена")
async def cancel_to_menu(message: Message, state: FSMContext):
    try:
        await state.clear()
        await message.answer(texts.CANCELLED, reply_markup=main_menu_kb())
    except Exception:
        log.exception("cancel_to_menu failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "↩️ В меню")
async def back_to_menu(message: Message, state: FSMContext):
    try:
        await state.clear()
        await message.answer(texts.MENU, reply_markup=main_menu_kb())
    except Exception:
        log.exception("back_to_menu failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "🧬 Персонаж")
async def character(message: Message, db):
    try:
        tg_id = message.from_user.id
        user = db.get_or_create_user(tg_id, message.from_user.username)
        db.ensure_progress(user["id"])
        p = db.get_progress(user["id"])

        muscles = p.get("muscles") or {}
        lvl = int(p.get("level", 1))
        xp = int(p.get("xp", 0))

        xp_to_next = 100 + lvl * 25

        def line(label: str, key: str) -> str:
            val = int(muscles.get(key, 0) or 0)
            return f"{label}: {render_bar(val)} {val}"

        muscle_lines = [
            line("🦵 Ноги", "legs"),
            line("🧱 Спина", "back"),
            line("🫀 Грудь", "chest"),
            line("🧍 Плечи", "shoulders"),
            line("💪 Руки", "arms"),
            line("🎯 Кор", "core"),
        ]

        achievements = p.get("achievements", [])
        achievements_count = len(achievements) if isinstance(achievements, list) else 0

        text = (
            "<b>Персонаж</b>\n"
            f"Уровень: <b>{lvl}</b>\n"
            f"XP: <b>{xp}/{xp_to_next}</b>\n"
            f"Достижений: <b>{achievements_count}</b>\n\n"
            "<b>Мышцы</b>\n"
            + "\n".join(muscle_lines)
        )

        await message.answer(text, reply_markup=main_menu_kb())
    except Exception:
        log.exception("character failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())

