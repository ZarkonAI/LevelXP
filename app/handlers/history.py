import logging
import re
from datetime import datetime
from typing import List, Optional

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import texts
from app.keyboards import (
    back_cancel_kb,
    back_menu_kb,
    confirm_edit_kb,
    history_action_kb,
    history_list_kb,
    main_menu_kb,
    repeat_options_kb,
)
from app.states import EditWorkoutStates, HistoryStates, QuickLogStates, TemplateStates

log = logging.getLogger("handlers.history")
router = Router()
INDEX_RE = re.compile(r"^(10|[1-9])\)")
EDIT_FILTER = StateFilter(
    EditWorkoutStates.waiting_weight,
    EditWorkoutStates.waiting_reps,
    EditWorkoutStates.waiting_sets,
    EditWorkoutStates.waiting_rest_single,
    EditWorkoutStates.waiting_rest_pattern,
    EditWorkoutStates.confirm,
)


def _parse_date(date_raw: str | None) -> str:
    if not date_raw:
        return "дата неизвестна"
    try:
        return datetime.fromisoformat(date_raw).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(date_raw)


def _format_rest_minutes(rest_seconds: int | float | None) -> str:
    return f"{float(rest_seconds or 0) / 60:g}"


def _extract_pattern_values(raw: str) -> Optional[List[float]]:
    tokens = re.findall(r"\d+(?:[\.,]\d+)?", (raw or "").strip())
    if not tokens:
        return None
    return [float(token.replace(",", ".")) for token in tokens]




def _strip_tech_id(value: str | None) -> str:
    return re.sub(r"\s*\(#\d+\)", "", str(value or "")).strip()

def _status_text(status: str | None) -> str:
    return texts.STATUS_DONE if status == "done" else texts.STATUS_PLANNED


async def _render_card(message: Message, state: FSMContext, db, user_id: int, workout_id: int):
    card = db.get_workout_card(user_id=user_id, workout_id=workout_id)
    if not card:
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
        return

    lines = [
        f"<b>{_parse_date(card.get('workout_date'))}</b> — <b>{_strip_tech_id(card.get('title') or 'Тренировка')}</b>",
        f"Статус: {_status_text(card.get('status'))}",
        f"Упражнение: {card.get('exercise_name') or 'Упражнение'}",
        f"Вес: {float(card.get('weight') or 0):g} кг",
        f"Повторы: {int(card.get('reps') or 0)}",
        f"Подходы: {int(card.get('sets_count') or 0)}",
        f"Отдых: {_format_rest_minutes(card.get('rest_seconds'))} мин",
    ]

    rest_pattern = card.get("rest_pattern")
    if isinstance(rest_pattern, list) and rest_pattern:
        pattern_minutes = ", ".join(f"{(float(s or 0) / 60):g}" for s in rest_pattern)
        lines.append(f"Отдых по подходам: {pattern_minutes}")

    await state.update_data(selected_workout_id=workout_id, mode=card.get("mode"))
    await state.set_state(HistoryStates.viewing_card)
    await message.answer("\n".join(lines), reply_markup=history_action_kb(card.get("status")))




@router.message(F.text == "↩️ В меню")
async def history_to_menu(message: Message, state: FSMContext):
    try:
        await state.clear()
        await message.answer(texts.MENU, reply_markup=main_menu_kb())
    except Exception:
        log.exception("history_to_menu failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "📒 История")
async def open_history(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        workouts = db.list_workouts(user_id=int(user["id"]), limit=10)
        if not workouts:
            await message.answer(texts.HISTORY_EMPTY, reply_markup=main_menu_kb())
            return

        history_map = {str(idx): int(workout["id"]) for idx, workout in enumerate(workouts[:10], start=1)}
        await state.update_data(history_map=history_map, history_workouts=workouts, last_workouts_count=len(workouts))
        await state.set_state(HistoryStates.browsing_list)
        await message.answer(texts.HISTORY_TITLE, reply_markup=history_list_kb(workouts))
    except Exception:
        log.exception("open_history failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(HistoryStates.browsing_list, F.text.regexp(INDEX_RE.pattern))
async def open_workout_details(message: Message, state: FSMContext, db):
    try:
        match = INDEX_RE.match(message.text or "")
        if not match:
            return

        idx = match.group(1)
        data = await state.get_data()
        history_map = data.get("history_map") or {}
        workout_id = history_map.get(idx)
        if not workout_id:
            await message.answer(texts.HISTORY_TITLE, reply_markup=history_list_kb(data.get("history_workouts") or []))
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        await _render_card(message, state, db, user_id=int(user["id"]), workout_id=int(workout_id))
    except Exception:
        log.exception("open_workout_details failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(HistoryStates.viewing_card, F.text == "🔁 Повторить")
async def repeat_from_history(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        selected_workout_id = data.get("selected_workout_id")
        if not selected_workout_id:
            await message.answer(texts.HISTORY_TITLE, reply_markup=main_menu_kb())
            return

        await state.set_state(HistoryStates.choosing_repeat_mode)
        await message.answer("Повторить тренировку? Выбери вариант:", reply_markup=repeat_options_kb())
    except Exception:
        log.exception("repeat_from_history failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(HistoryStates.choosing_repeat_mode, F.text == "✅ Точно так же")
async def repeat_from_history_exact(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        selected_workout_id = data.get("selected_workout_id")
        if not selected_workout_id:
            await message.answer(texts.HISTORY_TITLE, reply_markup=main_menu_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.ensure_progress(int(user["id"]))
        new_workout_id = db.clone_workout_as_new(user_id=int(user["id"]), workout_id=int(selected_workout_id))
        card = db.get_workout_card(user_id=int(user["id"]), workout_id=int(new_workout_id))
        award = db.award_and_update_progress(
            user_id=int(user["id"]),
            exercise_id=int(card.get("exercise_id") or 0),
            weight=float(card.get("weight") or 0),
            reps=int(card.get("reps") or 0),
            sets_count=int(card.get("sets_count") or 0),
        )
        db.update_workout_metrics(
            user_id=int(user["id"]),
            workout_id=int(new_workout_id),
            total_xp=int(award.get("xp_gain") or 0),
            total_sets=int(award.get("total_sets_for_workout") or 0),
            muscle_delta=award.get("muscle_delta") if isinstance(award.get("muscle_delta"), dict) else {},
            status="done",
        )
        await state.clear()
        await message.answer(texts.REPEAT_DONE, reply_markup=main_menu_kb())
    except Exception:
        log.exception("repeat_from_history_exact failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(HistoryStates.choosing_repeat_mode, F.text == "✏️ Изменить перед записью")
async def repeat_from_history_edit_before_save(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        selected_workout_id = data.get("selected_workout_id")
        if not selected_workout_id:
            await message.answer(texts.HISTORY_TITLE, reply_markup=main_menu_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        card = db.get_workout_card(user_id=int(user["id"]), workout_id=int(selected_workout_id))
        if not card:
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return

        rest_pattern = card.get("rest_pattern") if isinstance(card.get("rest_pattern"), list) else []
        prefill_rest_pattern_minutes = [float(s or 0) / 60 for s in rest_pattern]
        await state.update_data(
            mode=card.get("mode") or "strength",
            exercise_id=card.get("exercise_id"),
            exercise_name=card.get("exercise_name"),
            repeat_source_workout_id=int(selected_workout_id),
            prefill_weight=float(card.get("weight") or 0),
            prefill_reps=int(card.get("reps") or 0),
            prefill_sets=int(card.get("sets_count") or 0),
            prefill_rest_minutes=float(card.get("rest_seconds") or 0) / 60,
            prefill_rest_pattern_minutes=prefill_rest_pattern_minutes,
            prefill_rest_pattern_text=", ".join(f"{v:g}" for v in prefill_rest_pattern_minutes),
        )
        await state.set_state(QuickLogStates.enter_weight)
        await message.answer(
            "Введи вес (кг). Текущее: "
            f"{float(card.get('weight') or 0):g} кг. Введи новое или отправь '.' чтобы оставить как есть",
            reply_markup=back_cancel_kb(),
        )
    except Exception:
        log.exception("repeat_from_history_edit_before_save failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(HistoryStates.viewing_card, F.text.in_({"✅ Отметить выполненной", "☑️ Снять отметку"}))
async def toggle_workout_status(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        workout_id = data.get("selected_workout_id")
        if not workout_id:
            await message.answer(texts.HISTORY_TITLE, reply_markup=main_menu_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.toggle_workout_status_with_progress(user_id=int(user["id"]), workout_id=int(workout_id))
        await _render_card(message, state, db, user_id=int(user["id"]), workout_id=int(workout_id))
    except Exception:
        log.exception("toggle_workout_status failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(HistoryStates.viewing_card, F.text == "✏️ Исправить")
async def start_edit_workout(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        workout_id = data.get("selected_workout_id")
        if not workout_id:
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        card = db.get_workout_card(user_id=int(user["id"]), workout_id=int(workout_id))
        if not card:
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return

        await state.update_data(mode=card.get("mode"), previous_state=HistoryStates.viewing_card.state)
        await state.set_state(EditWorkoutStates.waiting_weight)
        await message.answer(texts.EDIT_START, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("start_edit_workout failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(EditWorkoutStates.waiting_weight)
async def edit_waiting_weight(message: Message, state: FSMContext):
    try:
        weight = float((message.text or "").strip().replace(",", "."))
        if weight < 0 or weight > 1000:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        await state.update_data(new_weight=weight)
        await state.set_state(EditWorkoutStates.waiting_reps)
        await message.answer(texts.EDIT_ENTER_REPS, reply_markup=back_cancel_kb())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("edit_waiting_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(EditWorkoutStates.waiting_reps)
async def edit_waiting_reps(message: Message, state: FSMContext):
    try:
        reps = int((message.text or "").strip())
        if reps < 1 or reps > 100:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        await state.update_data(new_reps=reps)
        await state.set_state(EditWorkoutStates.waiting_sets)
        await message.answer(texts.EDIT_ENTER_SETS, reply_markup=back_cancel_kb())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("edit_waiting_reps failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(EditWorkoutStates.waiting_sets)
async def edit_waiting_sets(message: Message, state: FSMContext):
    try:
        sets_count = int((message.text or "").strip())
        if sets_count < 1 or sets_count > 50:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return

        data = await state.get_data()
        await state.update_data(new_sets_count=sets_count)
        if data.get("mode") == "pattern":
            await state.set_state(EditWorkoutStates.waiting_rest_pattern)
            await message.answer(texts.EDIT_ENTER_REST_PATTERN, reply_markup=back_cancel_kb())
        else:
            await state.set_state(EditWorkoutStates.waiting_rest_single)
            await message.answer(texts.EDIT_ENTER_REST_SINGLE, reply_markup=back_cancel_kb())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("edit_waiting_sets failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(EditWorkoutStates.waiting_rest_single)
async def edit_waiting_rest(message: Message, state: FSMContext):
    try:
        minutes = float((message.text or "").strip().replace(",", "."))
        if minutes < 0 or minutes > 30:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        await state.update_data(new_rest_seconds=int(round(minutes * 60)), new_rest_pattern=None)
        await _show_edit_confirm(message, state)
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("edit_waiting_rest failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(EditWorkoutStates.waiting_rest_pattern)
async def edit_waiting_rest_pattern(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        sets_count = int(data.get("new_sets_count") or 1)
        expected = max(sets_count - 1, 0)
        values = _extract_pattern_values(message.text or "")
        if values is None or len(values) != expected or any(v < 0 or v > 30 for v in values):
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return

        rest_pattern = [int(round(v * 60)) for v in values]
        avg_rest = int(round(sum(rest_pattern) / len(rest_pattern))) if rest_pattern else 0
        await state.update_data(new_rest_seconds=avg_rest, new_rest_pattern=rest_pattern)
        await _show_edit_confirm(message, state)
    except Exception:
        log.exception("edit_waiting_rest_pattern failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


async def _show_edit_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(EditWorkoutStates.confirm)

    lines = [
        f"Вес: {float(data.get('new_weight') or 0):g} кг",
        f"Повторы: {int(data.get('new_reps') or 0)}",
        f"Подходы: {int(data.get('new_sets_count') or 0)}",
    ]
    if data.get("mode") == "pattern":
        pattern = data.get("new_rest_pattern") or []
        pattern_minutes = ", ".join(f"{(float(s) / 60):g}" for s in pattern) if pattern else "—"
        lines.append(f"Отдых по подходам: {pattern_minutes}")
    else:
        lines.append(f"Отдых: {_format_rest_minutes(data.get('new_rest_seconds'))} мин")

    await message.answer(f"{texts.EDIT_CONFIRM}\n\n" + "\n".join(lines), reply_markup=confirm_edit_kb())


@router.message(EditWorkoutStates.confirm, F.text == "✅ Сохранить правки")
async def save_edit_workout(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        workout_id = data.get("selected_workout_id")
        if not workout_id:
            await state.clear()
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.update_workout_entry(
            user_id=int(user["id"]),
            workout_id=int(workout_id),
            weight=float(data.get("new_weight") or 0),
            reps=int(data.get("new_reps") or 0),
            sets_count=int(data.get("new_sets_count") or 0),
            rest_seconds=int(data.get("new_rest_seconds") or 0),
            rest_pattern=data.get("new_rest_pattern") if isinstance(data.get("new_rest_pattern"), list) else None,
        )
        await message.answer(texts.EDIT_SAVED)
        await _render_card(message, state, db, user_id=int(user["id"]), workout_id=int(workout_id))
    except Exception:
        log.exception("save_edit_workout failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(HistoryStates.viewing_card, F.text == "💾 Сохранить как шаблон")
async def ask_template_name(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        if not data.get("selected_workout_id"):
            await message.answer(texts.HISTORY_TITLE, reply_markup=main_menu_kb())
            return
        await state.set_state(TemplateStates.waiting_name)
        await message.answer(texts.ASK_TEMPLATE_NAME, reply_markup=back_menu_kb())
    except Exception:
        log.exception("ask_template_name failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(TemplateStates.waiting_name)
async def save_template_name(message: Message, state: FSMContext, db):
    try:
        if message.text == "↩️ Назад":
            await history_back_from_template_name(message, state, db)
            return
        if message.text == "↩️ В меню":
            await state.clear()
            await message.answer(texts.MENU, reply_markup=main_menu_kb())
            return

        template_name = (message.text or "").strip()
        if not template_name:
            await message.answer(texts.ASK_TEMPLATE_NAME, reply_markup=back_menu_kb())
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


@router.message(HistoryStates.choosing_repeat_mode, F.text == "↩️ Назад")
async def repeat_mode_back(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        workout_id = data.get("selected_workout_id")
        if not workout_id:
            await state.set_state(HistoryStates.browsing_list)
            await message.answer(texts.HISTORY_TITLE, reply_markup=history_list_kb(data.get("history_workouts") or []))
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        await _render_card(message, state, db, user_id=int(user["id"]), workout_id=int(workout_id))
    except Exception:
        log.exception("repeat_mode_back failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(HistoryStates.viewing_card, F.text == "↩️ Назад")
async def history_back_to_list(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        await state.set_state(HistoryStates.browsing_list)
        await message.answer(texts.HISTORY_TITLE, reply_markup=history_list_kb(data.get("history_workouts") or []))
    except Exception:
        log.exception("history_back_to_list failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(EDIT_FILTER, F.text == "↩️ Назад")
async def history_back_from_edit(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        workout_id = data.get("selected_workout_id")
        if not workout_id:
            await state.set_state(HistoryStates.browsing_list)
            await message.answer(texts.HISTORY_TITLE, reply_markup=history_list_kb(data.get("history_workouts") or []))
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        await _render_card(message, state, db, user_id=int(user["id"]), workout_id=int(workout_id))
    except Exception:
        log.exception("history_back_from_edit failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(EDIT_FILTER, F.text == "❌ Отмена")
async def history_cancel_edit(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        workout_id = data.get("selected_workout_id")
        if not workout_id:
            await state.clear()
            await message.answer(texts.CANCELLED, reply_markup=main_menu_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        await _render_card(message, state, db, user_id=int(user["id"]), workout_id=int(workout_id))
    except Exception:
        log.exception("history_cancel_edit failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(TemplateStates.waiting_name, F.text == "↩️ Назад")
async def history_back_from_template_name(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        workout_id = data.get("selected_workout_id")
        if not workout_id:
            await state.clear()
            await message.answer(texts.MENU, reply_markup=main_menu_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        await _render_card(message, state, db, user_id=int(user["id"]), workout_id=int(workout_id))
    except Exception:
        log.exception("history_back_from_template_name failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
