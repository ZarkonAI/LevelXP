import logging
import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from app import texts
from app.keyboards import (
    back_cancel_kb,
    confirm_kb,
    main_menu_kb,
    muscle_choice_kb,
    exercises_kb,
    training_menu_kb,
)
from app.states import QuickLogStates

log = logging.getLogger("handlers.training")
router = Router()



MUSCLE_LABELS = {
    "legs": "🦵 Ноги",
    "back": "🧱 Спина",
    "chest": "🫀 Грудь",
    "shoulders": "🧍 Плечи",
    "arms": "💪 Руки",
    "core": "🎯 Кор",
}


def reward_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏋️ Добавить ещё"), KeyboardButton(text="🧬 Персонаж")],
            [KeyboardButton(text="↩️ В меню")],
        ],
        resize_keyboard=True,
    )


def award_xp_and_update_progress(db, user_id: int, exercise_id: int, weight: float, reps: int, sets_count: int) -> dict:
    progress = db.get_progress(user_id)
    exercise = db.get_exercise(exercise_id)

    volume = weight * reps * sets_count
    load_points = math.sqrt(max(0, volume))
    xp_gain = max(5, round(load_points * 0.8))

    level = int(progress.get("level") or 1)
    xp = int(progress.get("xp") or 0) + xp_gain
    xp_to_next = 100 + level * 25

    while xp >= xp_to_next:
        xp -= xp_to_next
        level += 1
        xp_to_next = 100 + level * 25

    current_muscles = dict(progress.get("muscles") or {})
    for muscle in ("legs", "back", "chest", "shoulders", "arms", "core"):
        current_muscles.setdefault(muscle, 0)

    muscle_map = exercise.get("muscle_map") or {}
    if not muscle_map:
        primary = exercise.get("primary_muscle")
        if primary:
            muscle_map = {primary: 1.0}

    growth = {}
    for muscle, coeff in muscle_map.items():
        gain = round(load_points * float(coeff))
        if gain <= 0:
            continue
        current_muscles[muscle] = int(current_muscles.get(muscle, 0)) + gain
        growth[muscle] = gain

    workouts_count = progress.get("workouts_count")
    total_sets = progress.get("total_sets")

    db.update_progress(
        user_id=user_id,
        level=level,
        xp=xp,
        muscles=current_muscles,
        workouts_count=(int(workouts_count) + 1) if workouts_count is not None else None,
        total_sets=(int(total_sets) + sets_count) if total_sets is not None else None,
    )

    top_growth = sorted(growth.items(), key=lambda item: item[1], reverse=True)[:3]

    return {
        "xp_gain": xp_gain,
        "level": level,
        "xp": xp,
        "xp_to_next": xp_to_next,
        "top_growth": top_growth,
    }

MUSCLE_MAP = {
    "🦵 Ноги": "legs",
    "🧱 Спина": "back",
    "🫀 Грудь": "chest",
    "🧍 Плечи": "shoulders",
    "💪 Руки": "arms",
    "🎯 Кор": "core",
}


@router.message(F.text == "🏋️ Тренировка")
async def training_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(texts.TRAINING_CHOOSE, reply_markup=training_menu_kb())


@router.message(F.text == "⚡ Быстрая запись")
async def quick_log_start(message: Message, state: FSMContext, db):
    try:
        exercises = db.list_exercises(limit=12)
        await state.set_state(QuickLogStates.choose_exercise)
        await state.update_data(exercises=exercises)
        await message.answer(texts.CHOOSE_EXERCISE, reply_markup=exercises_kb(exercises))
    except Exception:
        log.exception("quick_log_start failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "🏋️ Добавить ещё")
async def add_more(message: Message, state: FSMContext, db):
    await quick_log_start(message, state, db)


@router.message(F.text == "❌ Отмена")
async def cancel_any(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(texts.CANCELLED, reply_markup=main_menu_kb())


@router.message(F.text == "↩️ Назад")
async def back_any(message: Message, state: FSMContext):
    current = await state.get_state()
    if not current:
        await message.answer(texts.MENU, reply_markup=main_menu_kb())
        return

    await state.set_state(QuickLogStates.choose_exercise)
    data = await state.get_data()
    exercises = data.get("exercises") or []
    await message.answer(texts.CHOOSE_EXERCISE, reply_markup=exercises_kb(exercises))


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
        weight = float((message.text or "").replace(",", ".").strip())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
        return

    if weight < 0 or weight > 1000:
        await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
        return

    await state.update_data(weight=weight)
    await state.set_state(QuickLogStates.enter_reps)
    await message.answer(texts.ENTER_REPS, reply_markup=back_cancel_kb())


@router.message(QuickLogStates.enter_reps)
async def enter_reps(message: Message, state: FSMContext):
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


@router.message(QuickLogStates.enter_sets)
async def enter_sets(message: Message, state: FSMContext):
    try:
        sets_count = int((message.text or "").strip())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
        return

    if sets_count < 1 or sets_count > 50:
        await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
        return

    await state.update_data(sets_count=sets_count)
    await state.set_state(QuickLogStates.enter_rest)
    await message.answer(texts.ENTER_REST, reply_markup=back_cancel_kb())


@router.message(QuickLogStates.enter_rest)
async def enter_rest(message: Message, state: FSMContext):
    try:
        rest_minutes = int((message.text or "").strip())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
        return

    if rest_minutes < 0 or rest_minutes > 30:
        await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
        return

    await state.update_data(rest_minutes=rest_minutes, rest_seconds=rest_minutes * 60)
    await state.set_state(QuickLogStates.confirm)

    data = await state.get_data()
    summary = (
        f"{data['exercise_name']}\n"
        f"Вес: {data['weight']} кг\n"
        f"Повторы: {data['reps']}\n"
        f"Подходы: {data['sets_count']}\n"
        f"Отдых: {data['rest_minutes']} мин\n\n"
        "Сохранить?"
    )
    await message.answer(f"{texts.CONFIRM}\n\n{summary}", reply_markup=confirm_kb())


@router.message(QuickLogStates.confirm, F.text == "✏️ Изменить")
async def edit_quick_log(message: Message, state: FSMContext):
    data = await state.get_data()
    for key in ("weight", "reps", "sets_count", "rest_minutes", "rest_seconds"):
        data.pop(key, None)
    await state.set_data(data)
    await state.set_state(QuickLogStates.enter_weight)
    await message.answer(texts.ENTER_WEIGHT, reply_markup=back_cancel_kb())


@router.message(QuickLogStates.confirm, F.text == "✅ Сохранить")
async def save_quick_log(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.ensure_progress(user["id"])

        workout_id = db.create_workout(user["id"], title="Quick")
        item_id = db.create_workout_item(workout_id, int(data["exercise_id"]), order_index=1)
        db.create_set(
            workout_item_id=item_id,
            weight=float(data["weight"]),
            reps=int(data["reps"]),
            sets_count=int(data["sets_count"]),
            rest_seconds=int(data["rest_seconds"]),
        )

        reward = award_xp_and_update_progress(
            db=db,
            user_id=user["id"],
            exercise_id=int(data["exercise_id"]),
            weight=float(data["weight"]),
            reps=int(data["reps"]),
            sets_count=int(data["sets_count"]),
        )
        growth_lines = [
            f"• {MUSCLE_LABELS.get(muscle, muscle)} +{gain}"
            for muscle, gain in reward["top_growth"]
        ]
        growth_text = "\n".join(growth_lines) if growth_lines else "• Без заметного прироста"

        await state.clear()
        await message.answer(
            texts.REWARD_MESSAGE.format(
                xp_gain=reward["xp_gain"],
                level=reward["level"],
                muscles_growth=growth_text,
            ),
            reply_markup=reward_kb(),
        )
    except Exception:
        log.exception("save_quick_log failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.confirm)
async def confirm_fallback(message: Message):
    await message.answer(texts.CONFIRM, reply_markup=confirm_kb())
