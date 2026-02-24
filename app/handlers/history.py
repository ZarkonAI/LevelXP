import logging
import re
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import texts
from app.keyboards import back_to_menu_kb, history_details_kb, history_list_kb, main_menu_kb
from app.states import TemplateStates

log = logging.getLogger("handlers.history")
router = Router()

WORKOUT_ID_RE = re.compile(r"#(\d+)\)")


def _parse_date(date_raw: str | None) -> str:
    if not date_raw:
        return "дата неизвестна"
    try:
        return datetime.fromisoformat(date_raw).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(date_raw)


def _format_rest_minutes(rest_seconds: int | float | None) -> str:
    value = float(rest_seconds or 0) / 60
    return f"{value:g}"


@router.message(F.text == "📒 История")
async def open_history(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        workouts = db.list_workouts(user_id=int(user["id"]), limit=10)
        await state.update_data(history_workouts=workouts)

        if not workouts:
            await message.answer(texts.HISTORY_EMPTY, reply_markup=main_menu_kb())
            return

        await message.answer(texts.HISTORY_TITLE, reply_markup=history_list_kb(workouts))
    except Exception:
        log.exception("open_history failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text.regexp(WORKOUT_ID_RE.pattern))
async def open_workout_details(message: Message, state: FSMContext, db):
    try:
        text = message.text or ""
        if not text.startswith("🗓 "):
            return

        match = WORKOUT_ID_RE.search(text)
        if not match:
            return

        workout_id = int(match.group(1))
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        details = db.get_workout_details(workout_id=workout_id, user_id=int(user["id"]))
        if not details:
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return

        workout = details.get("workout") or {}
        items = details.get("items") or []

        lines = [f"<b>{_parse_date(workout.get('workout_date'))} — {workout.get('title', 'Workout')} (#{workout.get('id')})</b>"]
        for item in items:
            line = (
                f"{item.get('exercise_name', 'Упражнение')}: "
                f"{item.get('weight', 0)}кг x {item.get('reps', 0)} x {item.get('sets_count', 0)}, "
                f"отдых {_format_rest_minutes(item.get('rest_seconds'))} мин"
            )
            lines.append(line)
            rest_pattern = item.get("rest_pattern")
            if isinstance(rest_pattern, list) and rest_pattern:
                pattern_minutes = ", ".join(f"{(float(s) / 60):g}" for s in rest_pattern)
                lines.append(f"отдых по подходам: {pattern_minutes}")

        await state.update_data(selected_workout_id=workout_id)
        await message.answer("\n".join(lines), reply_markup=history_details_kb())
    except Exception:
        log.exception("open_workout_details failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "💾 Сохранить как шаблон")
async def ask_template_name(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        if not data.get("selected_workout_id"):
            await message.answer(texts.HISTORY_TITLE, reply_markup=main_menu_kb())
            return

        await state.set_state(TemplateStates.waiting_name)
        await message.answer(texts.ASK_TEMPLATE_NAME, reply_markup=back_to_menu_kb())
    except Exception:
        log.exception("ask_template_name failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(TemplateStates.waiting_name)
async def save_template_name(message: Message, state: FSMContext, db):
    try:
        template_name = (message.text or "").strip()
        if not template_name:
            await message.answer(texts.ASK_TEMPLATE_NAME, reply_markup=back_to_menu_kb())
            return

        data = await state.get_data()
        workout_id = data.get("selected_workout_id")
        if not workout_id:
            await state.clear()
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.create_template_from_workout(user_id=int(user["id"]), workout_id=int(workout_id), name=template_name)

        await state.clear()
        await message.answer(texts.TEMPLATE_SAVED, reply_markup=main_menu_kb())
    except Exception:
        log.exception("save_template_name failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "↩️ Назад")
async def history_back(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        workouts = data.get("history_workouts") or []
        if workouts:
            await message.answer(texts.HISTORY_TITLE, reply_markup=history_list_kb(workouts))
            return
        await message.answer(texts.MENU, reply_markup=main_menu_kb())
    except Exception:
        log.exception("history_back failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
