import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import texts
from app.keyboards import main_menu_kb, templates_confirm_kb, templates_list_kb

log = logging.getLogger("handlers.templates")
router = Router()

TEMPLATE_ID_RE = re.compile(r"#(\d+)\)")


@router.message(F.text == "🔁 Шаблоны")
async def open_templates(message: Message, state: FSMContext):
    try:
        await state.clear()
        await message.answer("Скоро", reply_markup=main_menu_kb())
    except Exception:
        log.exception("open_templates failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text.regexp(TEMPLATE_ID_RE.pattern))
async def select_template(message: Message, state: FSMContext, db):
    try:
        text = message.text or ""
        if not text.startswith("🔁 "):
            return

        match = TEMPLATE_ID_RE.search(text)
        if not match:
            return

        template_id = int(match.group(1))
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        template = db.get_template(user_id=int(user["id"]), template_id=template_id)
        if not template:
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return

        payload = template.get("payload") or []
        preview = []
        for item in payload[:3]:
            preview.append(
                f"• exercise_id={item.get('exercise_id')}: {item.get('weight', 0)}кг x {item.get('reps', 0)} x {item.get('sets_count', 0)}"
            )
        preview_text = "\n".join(preview) if preview else "• пустой шаблон"

        await state.update_data(selected_template_id=template_id)
        await message.answer(
            f"<b>{template.get('name', 'Шаблон')} (#{template.get('id')})</b>\n{preview_text}\n\n{texts.TEMPLATE_REPEAT_CONFIRM}",
            reply_markup=templates_confirm_kb(),
        )
    except Exception:
        log.exception("select_template failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "✅ Повторить")
async def repeat_template(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        selected_template_id = data.get("selected_template_id")
        if not selected_template_id:
            await message.answer(texts.TEMPLATES_TITLE, reply_markup=main_menu_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        template = db.get_template(user_id=int(user["id"]), template_id=int(selected_template_id))
        if not template:
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return

        db.create_workout_from_template(user_id=int(user["id"]), template_row=template)
        await state.clear()
        await message.answer(texts.TEMPLATE_REPEATED, reply_markup=main_menu_kb())
    except Exception:
        log.exception("repeat_template failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "↩️ Назад")
async def templates_back(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        templates = data.get("templates_list") or []
        if templates:
            await message.answer(texts.TEMPLATES_TITLE, reply_markup=templates_list_kb(templates))
            return
        await message.answer(texts.MENU, reply_markup=main_menu_kb())
    except Exception:
        log.exception("templates_back failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
