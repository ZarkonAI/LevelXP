import logging
import re
from typing import List, Optional
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from app import db as db_module
from app import texts
from app.keyboards import back_cancel_kb, confirm_kb, exercise_category_kb, exercises_kb, main_menu_kb, mode_kb, muscle_choice_kb, training_menu_kb
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


def _format_muscles(primary_muscle: str | None) -> str:
    return MUSCLE_LABELS.get(str(primary_muscle or "").strip().lower(), "—")


def _format_equipment(equipment: object) -> str:
    if isinstance(equipment, list):
        values = [str(item).strip() for item in equipment if str(item).strip()]
        return ", ".join(values) if values else "—"
    text = str(equipment or "").strip()
    return text or "—"


EXERCISE_PICK_RE = re.compile(r"^(\d+)\)")
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
    return [float(token.replace(",", ".")) for token in tokens]
def _prefill_hint(value: float | int | None, suffix: str = "") -> str:
    if value is None:
        return ""
    formatted = f"{float(value):g}" if isinstance(value, float) else str(value)
    return f"\nТекущее: {formatted}{suffix}. Введи новое или отправь '.' чтобы оставить как есть"
def _validate_name(name: str) -> bool:
    clean = (name or "").strip()
    if len(clean) < 2 or len(clean) > 60:
        return False
    if not re.fullmatch(r"[A-Za-zА-Яа-яЁё0-9\- ]+", clean):
        return False
    low = clean.lower()
    blocked = ("http", "https", "t.me", ".com", ".ru", ".net", ".org")
    return not any(token in low for token in blocked)
async def _to_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(texts.MENU, reply_markup=main_menu_kb())
async def _show_choose_exercise(message: Message, state: FSMContext):
    data = await state.get_data()
    exercises = data.get("exercises") or []
    ex_map = {
        str(idx): {
            "id": exercise.get("id"),
            "name": exercise.get("name"),
            "name_ru": exercise.get("name_ru"),
            "image_url": exercise.get("image_url"),
            "display_name": exercise.get("display_name"),
        }
        for idx, exercise in enumerate(exercises, start=1)
    }
    await state.update_data(ex_map=ex_map)
    await state.set_state(QuickLogStates.choose_exercise)
    await message.answer(texts.CHOOSE_EXERCISE, reply_markup=exercises_kb(exercises))


async def _goto_enter_weight(message: Message, state: FSMContext, data: dict):
    await state.set_state(QuickLogStates.enter_weight)
    await message.answer(f"{texts.ENTER_WEIGHT}{_prefill_hint(data.get('prefill_weight'), ' кг')}", reply_markup=back_cancel_kb())
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
@router.message(F.text == "❌ Отмена")
async def cancel_anywhere(message: Message, state: FSMContext):
    try:
        current = await state.get_state()
        if current and current.startswith("QuickLogStates:"):
            await _to_menu(message, state)
    except Exception:
        log.exception("cancel_anywhere failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.choose_mode, F.text == "↩️ В меню")
async def back_from_choose_mode(message: Message, state: FSMContext):
    await _to_menu(message, state)
@router.message(QuickLogStates.choose_category, F.text == "↩️ Назад")
async def back_from_choose_category(message: Message, state: FSMContext):
    await state.set_state(QuickLogStates.choose_mode)
    await message.answer(texts.CHOOSE_MODE, reply_markup=mode_kb())

@router.message(QuickLogStates.choose_exercise, F.text == "↩️ Назад")
async def back_from_choose_exercise(message: Message, state: FSMContext):
    await state.set_state(QuickLogStates.choose_category)
    await message.answer(texts.CHOOSE_CATEGORY, reply_markup=exercise_category_kb())
@router.message(QuickLogStates.search_query, F.text == "↩️ Назад")
async def back_from_search_query(message: Message, state: FSMContext):
    await state.set_state(QuickLogStates.choose_category)
    await message.answer(texts.CHOOSE_CATEGORY, reply_markup=exercise_category_kb())
@router.message(QuickLogStates.custom_name, F.text == "↩️ Назад")
async def back_from_custom_name(message: Message, state: FSMContext):
    await state.set_state(QuickLogStates.choose_category)
    await message.answer(texts.CHOOSE_CATEGORY, reply_markup=exercise_category_kb())
@router.message(QuickLogStates.custom_primary_muscle, F.text == "↩️ Назад")
async def back_from_custom_primary(message: Message, state: FSMContext):
    await state.set_state(QuickLogStates.custom_name)
    await message.answer(texts.ENTER_CUSTOM_NAME, reply_markup=back_cancel_kb())
@router.message(QuickLogStates.enter_weight, F.text == "↩️ Назад")
async def back_from_weight(message: Message, state: FSMContext):
    await _show_choose_exercise(message, state)
@router.message(QuickLogStates.enter_reps, F.text == "↩️ Назад")
async def back_from_reps(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(QuickLogStates.enter_weight)
    await message.answer(f"{texts.ENTER_WEIGHT}{_prefill_hint(data.get('prefill_weight'), ' кг')}", reply_markup=back_cancel_kb())
@router.message(QuickLogStates.enter_sets, F.text == "↩️ Назад")
async def back_from_sets(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(QuickLogStates.enter_reps)
    await message.answer(f"{texts.ENTER_REPS}{_prefill_hint(data.get('prefill_reps'))}", reply_markup=back_cancel_kb())
@router.message(QuickLogStates.enter_rest_single, F.text == "↩️ Назад")
async def back_from_rest_single(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(QuickLogStates.enter_sets)
    await message.answer(f"{texts.ENTER_SETS}{_prefill_hint(data.get('prefill_sets'))}", reply_markup=back_cancel_kb())
@router.message(QuickLogStates.enter_rest_pattern, F.text == "↩️ Назад")
async def back_from_rest_pattern(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(QuickLogStates.enter_sets)
    await message.answer(f"{texts.ENTER_SETS}{_prefill_hint(data.get('prefill_sets'))}", reply_markup=back_cancel_kb())
@router.message(QuickLogStates.confirm, F.text == "↩️ Назад")
async def back_from_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("mode") == "pattern":
        await state.set_state(QuickLogStates.enter_rest_pattern)
        await message.answer(f"{texts.ENTER_REST_PATTERN}{_prefill_hint(data.get('prefill_rest_pattern_text'), ' мин')}", reply_markup=back_cancel_kb())
    else:
        await state.set_state(QuickLogStates.enter_rest_single)
        await message.answer(f"{texts.ENTER_REST_SINGLE}{_prefill_hint(data.get('prefill_rest_minutes'), ' мин')}", reply_markup=back_cancel_kb())
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
        await state.update_data(mode=mode, exercises=[], selected_category=None)
        await state.set_state(QuickLogStates.choose_category)
        await message.answer(texts.CHOOSE_CATEGORY, reply_markup=exercise_category_kb())
    except Exception:
        log.exception("choose_mode failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.choose_category)
async def choose_category(message: Message, state: FSMContext, db):
    try:
        if message.text == "🔎 Поиск":
            await state.set_state(QuickLogStates.search_query)
            await message.answer(texts.SEARCH_PROMPT, reply_markup=back_cancel_kb())
            return
        if message.text == "➕ Своё упражнение":
            await state.set_state(QuickLogStates.custom_name)
            await message.answer(texts.ENTER_CUSTOM_NAME, reply_markup=back_cancel_kb())
            return

        selected_muscle = MUSCLE_MAP.get(message.text or "")
        if not selected_muscle:
            await message.answer(texts.CHOOSE_CATEGORY, reply_markup=exercise_category_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        exercise_lang = db.get_exercise_lang(user_id=int(user["id"]))
        exercises = db.list_exercises(user_id=int(user["id"]), limit=12, primary_muscle=selected_muscle, lang=exercise_lang)
        if not exercises:
            await message.answer(texts.SEARCH_EMPTY, reply_markup=exercise_category_kb())
            return

        await state.update_data(exercises=exercises, selected_category=selected_muscle)
        await _show_choose_exercise(message, state)
    except Exception:
        log.exception("choose_category failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())

@router.message(QuickLogStates.choose_exercise)
async def choose_exercise(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        ex_map = data.get("ex_map") or {}
        match = EXERCISE_PICK_RE.match((message.text or "").strip())
        selected = ex_map.get(match.group(1)) if match else None
        if not selected:
            await message.answer(texts.CHOOSE_EXERCISE_FROM_LIST, reply_markup=exercises_kb(data.get("exercises") or []))
            return
        display_name = str(selected.get("display_name") or selected.get("name") or "Упражнение")
        image_url = str(selected.get("image_url") or "").strip()
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        exercise_lang = db.get_exercise_lang(user_id=int(user["id"]))
        translate_mode = db.get_translate_mode(user_id=int(user["id"]))
        await state.update_data(
            exercise_id=selected["id"],
            exercise_name=display_name,
            exercise_display_name=display_name,
            image_url=image_url or None,
        )
        if image_url:
            try:
                await message.answer_photo(photo=image_url, caption=texts.TECHNIQUE_CAPTION.format(display_name=display_name))
            except Exception:
                await message.answer(f"{display_name}\n{texts.TECHNIQUE_LINK_PREFIX} {image_url}")

        if translate_mode and exercise_lang == "ru" and not str(selected.get("name_ru") or "").strip():
            await state.update_data(pending_exercise_id=selected["id"])
            await state.set_state(QuickLogStates.set_ru_name)
            await message.answer(texts.RU_NAME_PROMPT, reply_markup=back_cancel_kb())
            return

        await _goto_enter_weight(message, state, data)
    except Exception:
        log.exception("choose_exercise failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.set_ru_name, F.text == "↩️ Назад")
async def back_from_set_ru_name(message: Message, state: FSMContext):
    await _show_choose_exercise(message, state)


@router.message(QuickLogStates.set_ru_name)
async def set_ru_name(message: Message, state: FSMContext, db):
    try:
        value = (message.text or "").strip()
        data = await state.get_data()
        pending_exercise_id = data.get("pending_exercise_id")
        if pending_exercise_id and value != "-":
            db.update_exercise_name_ru(exercise_id=int(pending_exercise_id), name_ru=value)
        await _goto_enter_weight(message, state, data)
    except Exception:
        log.exception("set_ru_name failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.search_query)
async def search_query(message: Message, state: FSMContext, db):
    try:
        query = (message.text or "").strip()
        if not query:
            await message.answer(texts.SEARCH_PROMPT, reply_markup=back_cancel_kb())
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        exercise_lang = db.get_exercise_lang(user_id=int(user["id"]))
        exercises = db.list_exercises(user_id=int(user["id"]), limit=12, query=query, lang=exercise_lang)
        if not exercises:
            await message.answer(texts.SEARCH_EMPTY, reply_markup=back_cancel_kb())
            return
        await state.update_data(exercises=exercises)
        await _show_choose_exercise(message, state)
    except Exception:
        log.exception("search_query failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.custom_name)
async def custom_name(message: Message, state: FSMContext):
    try:
        exercise_name = (message.text or "").strip()
        if not exercise_name:
            await message.answer(texts.ENTER_CUSTOM_NAME, reply_markup=back_cancel_kb())
            return
        if not _validate_name(exercise_name):
            await state.set_state(QuickLogStates.custom_name)
            await message.answer(texts.ERR_EXERCISE_NAME, reply_markup=back_cancel_kb())
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
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        try:
            exercise = db.create_custom_exercise(int(user["id"]), exercise_name, primary_muscle)
        except ValueError:
            await message.answer(texts.ERR_EXERCISE_NAME, reply_markup=back_cancel_kb())
            await state.set_state(QuickLogStates.custom_name)
            return
        await state.update_data(exercise_id=exercise["id"], exercise_name=exercise.get("display_name"), primary_muscle=primary_muscle)
        await state.set_state(QuickLogStates.enter_weight)
        await message.answer(f"{texts.ENTER_WEIGHT}{_prefill_hint(data.get('prefill_weight'), ' кг')}", reply_markup=back_cancel_kb())
    except Exception:
        log.exception("custom_primary_muscle failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.enter_weight)
async def enter_weight(message: Message, state: FSMContext):
    try:
        raw = (message.text or "").strip()
        data = await state.get_data()
        if raw == "." and data.get("prefill_weight") is not None:
            weight = float(data.get("prefill_weight") or 0)
        else:
            weight = _parse_float(raw)
        if weight < 0 or weight > 1000:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        await state.update_data(weight=weight)
        await state.set_state(QuickLogStates.enter_reps)
        await message.answer(f"{texts.ENTER_REPS}{_prefill_hint(data.get('prefill_reps'))}", reply_markup=back_cancel_kb())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("enter_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.enter_reps)
async def enter_reps(message: Message, state: FSMContext):
    try:
        raw = (message.text or "").strip()
        data = await state.get_data()
        if raw == "." and data.get("prefill_reps") is not None:
            reps = int(data.get("prefill_reps") or 0)
        else:
            reps = int(raw)
        if reps < 1 or reps > 200:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        await state.update_data(reps=reps)
        await state.set_state(QuickLogStates.enter_sets)
        await message.answer(f"{texts.ENTER_SETS}{_prefill_hint(data.get('prefill_sets'))}", reply_markup=back_cancel_kb())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("enter_reps failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.enter_sets)
async def enter_sets(message: Message, state: FSMContext):
    try:
        raw = (message.text or "").strip()
        data = await state.get_data()
        if raw == "." and data.get("prefill_sets") is not None:
            sets_count = int(data.get("prefill_sets") or 0)
        else:
            sets_count = int(raw)
        if sets_count < 1 or sets_count > 50:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        await state.update_data(sets_count=sets_count)
        if data.get("mode") == "pattern":
            await state.set_state(QuickLogStates.enter_rest_pattern)
            hint = _prefill_hint(data.get("prefill_rest_pattern_text"), " мин") if data.get("prefill_rest_pattern_text") else ""
            await message.answer(f"{texts.ENTER_REST_PATTERN}{hint}", reply_markup=back_cancel_kb())
        else:
            await state.set_state(QuickLogStates.enter_rest_single)
            await message.answer(f"{texts.ENTER_REST_SINGLE}{_prefill_hint(data.get('prefill_rest_minutes'), ' мин')}", reply_markup=back_cancel_kb())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("enter_sets failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.enter_rest_single)
async def enter_rest_single(message: Message, state: FSMContext):
    try:
        raw = (message.text or "").strip()
        data = await state.get_data()
        if raw == "." and data.get("prefill_rest_minutes") is not None:
            minutes = float(data.get("prefill_rest_minutes") or 0)
        else:
            minutes = _parse_float(raw)
        if minutes < 0 or minutes > 30:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        rest_seconds = int(round(minutes * 60))
        await state.update_data(rest_minutes=minutes, rest_seconds=rest_seconds, rest_pattern_seconds=None)
        await _show_confirm(message, state)
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
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
        if raw == "." and isinstance(data.get("prefill_rest_pattern_minutes"), list):
            values = list(data.get("prefill_rest_pattern_minutes") or [])
        else:
            values = _extract_pattern_values(raw)
        if values is None:
            await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
            return
        if expected_length == 0:
            values = []
        if len(values) != expected_length or any(v < 0 or v > 30 for v in values):
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        rest_pattern_seconds = [int(round(v * 60)) for v in values]
        rest_seconds = int(round(sum(rest_pattern_seconds) / len(rest_pattern_seconds))) if rest_pattern_seconds else 0
        await state.update_data(rest_pattern_minutes=values, rest_pattern_seconds=rest_pattern_seconds, rest_seconds=rest_seconds)
        await _show_confirm(message, state)
    except Exception:
        log.exception("enter_rest_pattern failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
async def _show_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(QuickLogStates.confirm)
    lines = [
        f"{data.get('exercise_display_name') or data['exercise_name']}",
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
    if data.get("image_url"):
        lines.append(f"{texts.TECHNIQUE_LINK_PREFIX} {data['image_url']}")
    await message.answer(f"{texts.CONFIRM}\n\n" + "\n".join(lines), reply_markup=confirm_kb())
@router.message(QuickLogStates.confirm, F.text == "✏️ Изменить")
async def edit_quick_log(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        for key in ("weight", "reps", "sets_count", "rest_minutes", "rest_seconds", "rest_pattern_minutes", "rest_pattern_seconds"):
            data.pop(key, None)
        await state.set_data(data)
        await state.set_state(QuickLogStates.enter_weight)
        await message.answer(f"{texts.ENTER_WEIGHT}{_prefill_hint(data.get('prefill_weight'), ' кг')}", reply_markup=back_cancel_kb())
    except Exception:
        log.exception("edit_quick_log failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.confirm, F.text == "✅ Сохранить")
async def save_quick_log(message: Message, state: FSMContext, db):
    current_state = await state.get_state()
    if not current_state:
        return
    data = await state.get_data()
    if data.get("saved"):
        return
    await state.update_data(saved=True)
    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.ensure_progress(user["id"])
        template_payload = data.get("template_edit_payload") if isinstance(data.get("template_edit_payload"), list) else None
        if template_payload is not None:
            payload = list(template_payload)
            first = payload[0] if payload else {}
            first["weight"] = float(data["weight"])
            first["reps"] = int(data["reps"])
            first["sets_count"] = int(data["sets_count"])
            first["rest_seconds"] = int(data["rest_seconds"])
            first["rest_pattern"] = data.get("rest_pattern_seconds")
            if payload:
                payload[0] = first
            workout_id = db.create_workout(user["id"], title=_build_workout_title(data), mode="template", status="planned")
            for idx, item in enumerate(payload, start=1):
                if item.get("exercise_id") is None:
                    continue
                item_id = db.create_workout_item(workout_id, int(item["exercise_id"]), order_index=idx)
                db.create_set(
                    workout_item_id=item_id,
                    weight=float(item.get("weight") or 0),
                    reps=int(item.get("reps") or 0),
                    sets_count=int(item.get("sets_count") or 0),
                    rest_seconds=int(item.get("rest_seconds") or 0),
                    rest_pattern_seconds=item.get("rest_pattern") if isinstance(item.get("rest_pattern"), list) else None,
                )
        else:
            workout_id = db.create_workout(
                user["id"],
                title=_build_workout_title(data),
                mode=data["mode"],
                status="planned" if data.get("repeat_source_workout_id") else "done",
                source_workout_id=int(data["repeat_source_workout_id"]) if data.get("repeat_source_workout_id") else None,
            )
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
        log.exception("save_quick_log failed")
        await state.clear()
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
        return
    try:
        if template_payload is not None:
            total_xp = 0
            total_sets = 0
            muscle_delta = {}
            top = []
            for idx, item in enumerate(template_payload):
                ex_id = item.get("exercise_id")
                if ex_id is None:
                    continue
                award_item = db.award_and_update_progress(
                    user_id=int(user["id"]),
                    exercise_id=int(ex_id),
                    weight=float(data["weight"]) if idx == 0 else float(item.get("weight") or 0),
                    reps=int(data["reps"]) if idx == 0 else int(item.get("reps") or 0),
                    sets_count=int(data["sets_count"]) if idx == 0 else int(item.get("sets_count") or 0),
                )
                total_xp += int(award_item.get("xp_gain") or 0)
                total_sets += int(award_item.get("total_sets_for_workout") or 0)
                for m, val in (award_item.get("muscle_delta") or {}).items():
                    muscle_delta[m] = int(muscle_delta.get(m, 0)) + int(val)
                top.extend(award_item.get("muscle_gains_sorted_top3") or [])
            db.update_workout_metrics(
                user_id=int(user["id"]),
                workout_id=int(workout_id),
                total_xp=total_xp,
                total_sets=total_sets,
                muscle_delta=muscle_delta,
                status="done",
            )
            progress = db.get_progress(int(user["id"]))
            reward_text = (
                "<b>LevelXP · Награда</b>\n"
                f"+<b>{total_xp} XP</b> | Уровень: <b>{progress['level']}</b>\n"
                f"XP: <b>{progress['xp']}/{100 + int(progress['level']) * 25}</b>\n\n"
                "<b>Прокачка</b>\n"
                + ("\n".join([f"- {MUSCLE_LABELS.get(m, '🏋️ Нагрузка')}: +{g}" for m, g in top[:3]]) if top else "- 🏋️ Общая нагрузка учтена")
                + "\n\nПрогресс засчитан."
            )
        else:
            award = db.award_and_update_progress(
                user_id=int(user["id"]),
                exercise_id=int(data["exercise_id"]),
                weight=float(data["weight"]),
                reps=int(data["reps"]),
                sets_count=int(data["sets_count"]),
            )
            db.update_workout_metrics(
                user_id=int(user["id"]),
                workout_id=int(workout_id),
                total_xp=int(award.get("xp_gain") or 0),
                total_sets=int(award.get("total_sets_for_workout") or 0),
                muscle_delta=award.get("muscle_delta") if isinstance(award.get("muscle_delta"), dict) else {},
                status="done",
            )
            top = award.get("muscle_gains_sorted_top3") or []
            pump_text = "\n".join([f"- {MUSCLE_LABELS.get(m, '🏋️ Нагрузка')}: +{g}" for m, g in top]) if top else "- 🏋️ Общая нагрузка учтена"
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
            lines = [texts.ACHIEVEMENT_UNLOCKED.format(name=db_module.ACHIEVEMENTS_META.get(aid, aid)) for aid in new_achievements]
            await message.answer("\n".join(lines), reply_markup=main_menu_kb())
    except Exception:
        log.exception("award_and_update_progress failed")
        await state.clear()
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.confirm)
async def confirm_fallback(message: Message):
    await message.answer(texts.CONFIRM, reply_markup=confirm_kb())
