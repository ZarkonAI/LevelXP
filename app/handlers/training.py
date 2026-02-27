import logging
import re
from typing import List, Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import texts
from app.keyboards import (
    back_cancel_kb,
    confirm_kb,
    exercises_kb,
    main_menu_kb,
    mode_kb,
    muscle_choice_kb,
    training_menu_kb,
)
from app import db as db_module
from app.states import QuickLogStates

log = logging.getLogger("handlers.training")
router = Router()

MUSCLE_MAP = {
    "🦵 Ноги": "legs",
    "🧱 Спина": "back",
    "🫀 Грудь": "chest",
    "🧍 Плечи": "shoulders",
    "💪 Руки": "arms",
    "🎯 Кор": "core",
}

MODE_STRENGTH = "🏋️ Силовая (одинаковый отдых)"
MODE_PATTERN = "🔁 Отдых по подходам"

MUSCLE_LABELS = {"legs": "🦵 Ноги", "core": "🎯 Кор", "back": "🧱 Спина", "chest": "🫀 Грудь", "shoulders": "🧍 Плечи", "arms": "💪 Руки"}


def _trim_title(title: str, max_len: int = 80) -> str:
    value = (title or "").strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "…"


def _build_workout_title(data: dict) -> str:
    exercise_name = str(data.get("exercise_name") or "Тренировка")
    weight = float(data.get("weight") or 0)
    reps = int(data.get("reps") or 0)
    sets_count = int(data.get("sets_count") or 0)

    if weight == 0:
        title = f"{exercise_name} · {reps}×{sets_count}"
    else:
        title = f"{exercise_name} · {weight:g}кг×{reps}×{sets_count}"

    if data.get("mode") == "pattern":
        title += " · rest pattern"
    else:
        rest_minutes = data.get("rest_minutes")
        if rest_minutes is not None:
            title += f" · rest {float(rest_minutes):g}м"

    return _trim_title(title)


def _parse_float(raw: str) -> float:
    return float(raw.strip().replace(",", "."))


def _extract_pattern_values(raw: str) -> Optional[List[float]]:
    raw = (raw or "").strip()
    if not raw:
        return []
    tokens = re.findall(r"\d+(?:[\.,]\d+)?", raw)
    if not tokens:
        return None

    values: List[float] = []
    for token in tokens:
        values.append(float(token.replace(",", ".")))
    return values


@router.message(F.text == "🏋️ Тренировка")
async def training_menu(message: Message, state: FSMContext):
    try:
        await state.clear()
        await message.answer(texts.TRAINING_CHOOSE, reply_markup=training_menu_kb())
    except Exception:
        log.exception("training_menu failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "⚡ Быстрая запись")
async def quick_log_start(message: Message, state: FSMContext):
    try:
        await state.clear()
        await state.set_state(QuickLogStates.choose_mode)
        await message.answer(texts.CHOOSE_MODE, reply_markup=mode_kb())
    except Exception:
        log.exception("quick_log_start failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "↩️ Назад")
async def back_any(message: Message, state: FSMContext):
    try:
        current = await state.get_state()
        if not current:
            await message.answer(texts.MENU, reply_markup=main_menu_kb())
            return

        await state.set_state(QuickLogStates.choose_exercise)
        data = await state.get_data()
        exercises = data.get("exercises") or []
        await message.answer(texts.CHOOSE_EXERCISE, reply_markup=exercises_kb(exercises))
    except Exception:
        log.exception("back_any failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.choose_mode)
async def choose_mode(message: Message, state: FSMContext, db):
    try:
        if message.text == MODE_STRENGTH:
            mode = "strength"
        elif message.text == MODE_PATTERN:
            mode = "pattern"
        else:
            await message.answer(texts.CHOOSE_MODE, reply_markup=mode_kb())
            return

        exercises = db.list_exercises(limit=12)
        await state.update_data(mode=mode, exercises=exercises)
        await state.set_state(QuickLogStates.choose_exercise)
        await message.answer(texts.CHOOSE_EXERCISE, reply_markup=exercises_kb(exercises))
    except Exception:
        log.exception("choose_mode failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.choose_exercise)
async def choose_exercise(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        exercises = data.get("exercises") or []
        by_name = {exercise.get("name"): exercise for exercise in exercises if exercise.get("name")}

        if message.text == "➕ Своё упражнение":
            await state.set_state(QuickLogStates.custom_name)
            await message.answer(texts.ENTER_CUSTOM_NAME, reply_markup=back_cancel_kb())
            return

        selected = by_name.get(message.text)
        if not selected:
            await message.answer(texts.CHOOSE_EXERCISE, reply_markup=exercises_kb(exercises))
            return

        await state.update_data(exercise_id=selected["id"], exercise_name=selected["name"])
        await state.set_state(QuickLogStates.enter_weight)
        await message.answer(texts.ENTER_WEIGHT, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("choose_exercise failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.custom_name)
async def custom_name(message: Message, state: FSMContext):
    try:
        exercise_name = (message.text or "").strip()
        if not exercise_name:
            await message.answer(texts.ENTER_CUSTOM_NAME, reply_markup=back_cancel_kb())
            return

        await state.update_data(exercise_name=exercise_name)
        await state.set_state(QuickLogStates.custom_primary_muscle)
        await message.answer(texts.CHOOSE_PRIMARY_MUSCLE, reply_markup=muscle_choice_kb())
    except Exception:
        log.exception("custom_name failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.custom_primary_muscle)
async def custom_primary_muscle(message: Message, state: FSMContext, db):
    try:
        primary_muscle = MUSCLE_MAP.get(message.text or "")
        if not primary_muscle:
            await message.answer(texts.CHOOSE_PRIMARY_MUSCLE, reply_markup=muscle_choice_kb())
            return

        data = await state.get_data()
        exercise_name = data.get("exercise_name")
        if not exercise_name:
            await state.set_state(QuickLogStates.custom_name)
            await message.answer(texts.ENTER_CUSTOM_NAME, reply_markup=back_cancel_kb())
            return

        exercise = db.create_custom_exercise(exercise_name, primary_muscle)
        await state.update_data(exercise_id=exercise["id"], exercise_name=exercise["name"], primary_muscle=primary_muscle)
        await state.set_state(QuickLogStates.enter_weight)
        await message.answer(texts.ENTER_WEIGHT, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("custom_primary_muscle failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.enter_weight)
async def enter_weight(message: Message, state: FSMContext):
    try:
        try:
            weight = _parse_float(message.text or "")
        except (TypeError, ValueError):
            await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
            return

        if weight < 0 or weight > 1000:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return

        await state.update_data(weight=weight)
        await state.set_state(QuickLogStates.enter_reps)
        await message.answer(texts.ENTER_REPS, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("enter_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.enter_reps)
async def enter_reps(message: Message, state: FSMContext):
    try:
        try:
            reps = int((message.text or "").strip())
        except (TypeError, ValueError):
            await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
            return

        if reps < 1 or reps > 200:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return

        await state.update_data(reps=reps)
        await state.set_state(QuickLogStates.enter_sets)
        await message.answer(texts.ENTER_SETS, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("enter_reps failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.enter_sets)
async def enter_sets(message: Message, state: FSMContext):
    try:
        try:
            sets_count = int((message.text or "").strip())
        except (TypeError, ValueError):
            await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
            return

        if sets_count < 1 or sets_count > 50:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return

        data = await state.get_data()
        await state.update_data(sets_count=sets_count)
        if data.get("mode") == "pattern":
            await state.set_state(QuickLogStates.enter_rest_pattern)
            await message.answer(texts.ENTER_REST_PATTERN, reply_markup=back_cancel_kb())
        else:
            await state.set_state(QuickLogStates.enter_rest_single)
            await message.answer(texts.ENTER_REST_SINGLE, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("enter_sets failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.enter_rest_single)
async def enter_rest_single(message: Message, state: FSMContext):
    try:
        try:
            minutes = _parse_float(message.text or "")
        except (TypeError, ValueError):
            await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
            return

        if minutes < 0 or minutes > 30:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return

        rest_seconds = int(round(minutes * 60))
        await state.update_data(rest_minutes=minutes, rest_seconds=rest_seconds, rest_pattern_seconds=None)
        await _show_confirm(message, state)
    except Exception:
        log.exception("enter_rest_single failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.enter_rest_pattern)
async def enter_rest_pattern(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        sets_count = int(data.get("sets_count", 1))
        expected_length = max(sets_count - 1, 0)

        raw = (message.text or "").strip()
        values = _extract_pattern_values(raw)
        if values is None:
            await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
            return

        if expected_length == 0:
            values = []

        if len(values) != expected_length:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return

        if any(v < 0 or v > 30 for v in values):
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return

        rest_pattern_seconds = [int(round(v * 60)) for v in values]
        rest_seconds = int(round(sum(rest_pattern_seconds) / len(rest_pattern_seconds))) if rest_pattern_seconds else 0

        await state.update_data(
            rest_pattern_minutes=values,
            rest_pattern_seconds=rest_pattern_seconds,
            rest_seconds=rest_seconds,
        )
        await _show_confirm(message, state)
    except Exception:
        log.exception("enter_rest_pattern failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


async def _show_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(QuickLogStates.confirm)

    lines = [
        f"{data['exercise_name']}",
        f"Вес: {data['weight']} кг",
        f"Повторы: {data['reps']}",
        f"Подходы: {data['sets_count']}",
    ]

    if data.get("mode") == "pattern":
        minutes_values = data.get("rest_pattern_minutes") or []
        pattern_str = ", ".join(str(v).replace(".", ",") for v in minutes_values) if minutes_values else "—"
        lines.append(f"Отдых по подходам: {pattern_str}")
    else:
        lines.append(f"Отдых: {str(data.get('rest_minutes', 0)).replace('.', ',')} мин")

    summary = "\n".join(lines)
    await message.answer(f"{texts.CONFIRM}\n\n{summary}", reply_markup=confirm_kb())


@router.message(QuickLogStates.confirm, F.text == "✏️ Изменить")
async def edit_quick_log(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        for key in (
            "weight",
            "reps",
            "sets_count",
            "rest_minutes",
            "rest_seconds",
            "rest_pattern_minutes",
            "rest_pattern_seconds",
        ):
            data.pop(key, None)
        await state.set_data(data)
        await state.set_state(QuickLogStates.enter_weight)
        await message.answer(texts.ENTER_WEIGHT, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("edit_quick_log failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.confirm, F.text == "✅ Сохранить")
async def save_quick_log(message: Message, state: FSMContext, db):
    current_state = await state.get_state()
    if not current_state:
        log.info("save_quick_log ignored: state already cleared")
        return

    data = await state.get_data()
    if data.get("saved"):
        log.info("save_quick_log ignored: already saved")
        return

    await state.update_data(saved=True)

    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.ensure_progress(user["id"])

        workout_title = _build_workout_title(data)
        workout_id = db.create_workout(user["id"], title=workout_title, mode=data["mode"])
        try:
            item_id = db.create_workout_item(workout_id, int(data["exercise_id"]), order_index=1)
            db.create_set(
                workout_item_id=item_id,
                weight=float(data["weight"]),
                reps=int(data["reps"]),
                sets_count=int(data["sets_count"]),
                rest_seconds=int(data["rest_seconds"]),
                rest_pattern_seconds=data.get("rest_pattern_seconds"),
            )
        except Exception:
            log.exception("save_quick_log failed while inserting workout_items/sets")
            await state.clear()
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return
    except Exception:
        log.exception("save_quick_log failed")
        await state.clear()
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
        return

    try:
        award = db.award_and_update_progress(
            user_id=int(user["id"]),
            exercise_id=int(data["exercise_id"]),
            weight=float(data["weight"]),
            reps=int(data["reps"]),
            sets_count=int(data["sets_count"]),
        )
        top = award.get("muscle_gains_sorted_top3") or []
        if top:
            lines = [
                f"- {MUSCLE_LABELS.get(muscle, '🏋️ Нагрузка')}: +{gain}"
                for muscle, gain in top
            ]
            pump_text = "\n".join(lines)
        else:
            pump_text = "- 🏋️ Общая нагрузка учтена"

        reward_text = (
            "<b>LevelXP · Награда</b>\n"
            f"+<b>{award['xp_gain']} XP</b> | Уровень: <b>{award['level_new']}</b>\n"
            f"XP: <b>{award['xp_new']}/{award['xp_to_next']}</b>\n\n"
            "<b>Прокачка</b>\n"
            f"{pump_text}\n\n"
            "Прогресс засчитан."
        )
        await state.clear()
        await message.answer(reward_text, reply_markup=main_menu_kb())

        new_achievements = db.check_and_award_achievements(int(user["id"]))
        if new_achievements:
            lines = [
                texts.ACHIEVEMENT_UNLOCKED.format(name=db_module.ACHIEVEMENTS_META.get(achievement_id, achievement_id))
                for achievement_id in new_achievements
            ]
            await message.answer("\n".join(lines), reply_markup=main_menu_kb())
    except Exception:
        log.exception("award_and_update_progress failed")
        await state.clear()
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.confirm)
async def confirm_fallback(message: Message):
    try:
        await message.answer(texts.CONFIRM, reply_markup=confirm_kb())
    except Exception:
        log.exception("confirm_fallback failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
