import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import texts
from app.db import ACHIEVEMENTS_META
from app.keyboards import main_menu_kb

log = logging.getLogger("handlers.achievements")
router = Router()


@router.message(F.text == "🏆 Достижения")
async def show_achievements(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.ensure_progress(int(user["id"]))
        progress = db.get_progress(int(user["id"]))
        achievement_ids = progress.get("achievements", [])
        if not isinstance(achievement_ids, list):
            achievement_ids = []

        if not achievement_ids:
            text = f"{texts.ACHIEVEMENTS_TITLE}\n\n{texts.ACHIEVEMENTS_EMPTY}"
            await message.answer(text, reply_markup=main_menu_kb())
            return

        lines = [texts.ACHIEVEMENTS_TITLE, ""]
        for aid in achievement_ids:
            title = ACHIEVEMENTS_META.get(str(aid), str(aid))
            lines.append(f"- 🏆 {title}")
        await message.answer("\n".join(lines), reply_markup=main_menu_kb())
    except Exception:
        log.exception("show_achievements failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
