import logging
import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import db as db_module
from app import texts
from app.keyboards import back_cancel_kb, continue_back_kb, main_menu_kb, templates_confirm_kb, templates_list_kb
from app.states import QuickLogStates, TemplateBrowseStates

log = logging.getLogger("handlers.templates")
router = Router()
INDEX_RE = re.compile(r"^(\d+)\)")
MUSCLE_LABELS = {"legs": "🦵 Ноги", "core": "🎯 Кор", "back": "🧱 Спина", "chest": "🫀 Грудь", "shoulders": "🧍 Плечи", "arms": "💪 Руки"}


def _load_exercise_image_url(db, exercise_id: int | None) -> str:
    if not exercise_id:
        return ""
    try:
        res = (
            db.client.table("exercises")
            .select("image_url")
            .eq("id", int(exercise_id))
            .limit(1)
            .execute()
        )
        return str((res.data or [{}])[0].get("image_url") or "").strip()
    except Exception:
        return ""


def _format_payload(payload: list[dict], db) -> str:
    if not payload:
        return "• пустой шаблон"
    lines = []
    for idx, item in enumerate(payload, start=1):
        ex_name = "Упражнение"
        ex_id = item.get("exercise_id")
        if ex_id is not None:
            try:
                ex_name = str(db.get_exercise(int(ex_id)).get("display_name") or ex_name)
            except Exception:
                pass
        lines.append(f"{idx}. {ex_name} — {float(item.get('weight') or 0):g}кг × {int(item.get('reps') or 0)} × {int(item.get('sets_count') or 0)}")
        image_url = _load_exercise_image_url(db, ex_id)
        if image_url:
            lines.append(f"   {_technique_line(image_url)}")
    return "\n".join(lines)


def _technique_line(image_url: str) -> str:
    return f"{texts.TECHNIQUE_LINK_PREFIX} {image_url}"


def _format_template_edit_intro(item: dict, idx: int, total: int, exercise_name: str) -> str:
    rest_pattern = item.get("rest_pattern") if isinstance(item.get("rest_pattern"), list) else []
    if rest_pattern:
        rest_text = f"паттерн {', '.join(f'{float(s or 0) / 60:g}' for s in rest_pattern)} мин"
    else:
        rest_text = f"{float(item.get('rest_seconds') or 0) / 60:g} мин"
    return (
        f"Шаблон: упражнение {idx}/{total} — {exercise_name}\n"
        f"Было: {float(item.get('weight') or 0):g}кг × {int(item.get('reps') or 0)} × {int(item.get('sets_count') or 0)} | отдых: {rest_text}\n"
        "Введи новое или '.' чтобы оставить как есть"
    )


def _format_delta_warning(db, total_xp: int, muscle_delta: dict) -> str:
    return "<b>Подтверждение</b>\n" + db.format_delta(total_xp=total_xp, muscle_delta=muscle_delta)


async def _show_template_card(message: Message, state: FSMContext, db, user_id: int, template_id: int):
    template = db.get_template(user_id=user_id, template_id=template_id)
    if not template:
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
        return
    payload = template.get("payload") if isinstance(template.get("payload"), list) else []
    await state.update_data(selected_template_id=template_id)
    await state.set_state(TemplateBrowseStates.confirming)
    await message.answer(
        f"<b>{template.get('name', 'Шаблон')}</b>\n\n{_format_payload(payload, db)}",
        reply_markup=templates_confirm_kb(),
    )


@router.message(F.text == "🔁 Шаблоны")
async def open_templates(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        templates = db.list_templates(user_id=int(user["id"]))
        if not templates:
            await message.answer(texts.TEMPLATES_EMPTY, reply_markup=main_menu_kb())
            return

        templates_map = {str(idx): int(row["id"]) for idx, row in enumerate(templates, start=1)}
        await state.update_data(templates_list=templates, templates_map=templates_map)
        await state.set_state(TemplateBrowseStates.browsing)
        await message.answer(texts.TEMPLATES_TITLE, reply_markup=templates_list_kb(templates))
    except Exception:
        log.exception("open_templates failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(TemplateBrowseStates.browsing, F.text.regexp(INDEX_RE.pattern))
async def select_template(message: Message, state: FSMContext, db):
    try:
        match = INDEX_RE.match(message.text or "")
        if not match:
            return
        idx = match.group(1)
        data = await state.get_data()
        template_id = (data.get("templates_map") or {}).get(idx)
        if not template_id:
            await message.answer(texts.TEMPLATES_TITLE, reply_markup=templates_list_kb(data.get("templates_list") or []))
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        await _show_template_card(message, state, db, user_id=int(user["id"]), template_id=int(template_id))
    except Exception:
        log.exception("select_template failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(TemplateBrowseStates.confirming, F.text == "✅ Применить")
async def ask_apply_template_confirm(message: Message, state: FSMContext, db):
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

        payload = template.get("payload") if isinstance(template.get("payload"), list) else []
        total_xp, muscle_delta, _ = db.compute_delta_from_payload(payload, user_id=int(user["id"]))
        await state.update_data(confirm_template_payload=payload)
        await state.set_state(TemplateBrowseStates.confirming_apply)
        await message.answer(_format_delta_warning(db, total_xp, muscle_delta), reply_markup=continue_back_kb())
    except Exception:
        log.exception("ask_apply_template_confirm failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(TemplateBrowseStates.confirming_apply, F.text == "✅ Продолжить")
async def apply_template(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        selected_template_id = data.get("selected_template_id")
        if not selected_template_id:
            await message.answer(texts.TEMPLATES_TITLE, reply_markup=main_menu_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.ensure_progress(int(user["id"]))
        template = db.get_template(user_id=int(user["id"]), template_id=int(selected_template_id))
        if not template:
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return

        workout_id = db.create_workout_from_template(user_id=int(user["id"]), template_row=template)
        payload = template.get("payload") if isinstance(template.get("payload"), list) else []
        total_xp, muscle_delta, total_sets = db.compute_delta_from_payload(payload, user_id=int(user["id"]))

        top = sorted(muscle_delta.items(), key=lambda x: x[1], reverse=True)[:3]
        for item in payload:
            ex_id = item.get("exercise_id")
            if ex_id is None:
                continue
            db.award_and_update_progress(
                user_id=int(user["id"]),
                exercise_id=int(ex_id),
                weight=float(item.get("weight") or 0),
                reps=int(item.get("reps") or 0),
                sets_count=int(item.get("sets_count") or 0),
            )

        db.update_workout_metrics(int(user["id"]), int(workout_id), total_xp=total_xp, total_sets=total_sets, muscle_delta=muscle_delta, status="done")
        progress = db.get_progress(int(user["id"]))
        reward_text = (
            "<b>FitXP · Награда</b>\n"
            f"+<b>{total_xp} XP</b> | Уровень: <b>{progress['level']}</b>\n"
            f"XP: <b>{progress['xp']}/{100 + int(progress['level']) * 25}</b>\n\n"
            "<b>Прокачка</b>\n"
            + ("\n".join([f"- {MUSCLE_LABELS.get(m, '🏋️ Нагрузка')}: +{g}" for m, g in top]) if top else "- 🏋️ Общая нагрузка учтена")
            + "\n\nПрогресс засчитан."
        )
        await state.clear()
        await message.answer(reward_text, reply_markup=main_menu_kb())
        new_achievements = db.check_and_award_achievements(int(user["id"]))
        if new_achievements:
            lines = [texts.ACHIEVEMENT_UNLOCKED.format(name=db_module.ACHIEVEMENTS_META.get(aid, aid)) for aid in new_achievements]
            await message.answer("\n".join(lines), reply_markup=main_menu_kb())
    except Exception:
        log.exception("apply_template failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(TemplateBrowseStates.confirming, F.text == "✏️ Изменить перед применением")
async def edit_template_before_apply(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        template_id = data.get("selected_template_id")
        if not template_id:
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        template = db.get_template(user_id=int(user["id"]), template_id=int(template_id))
        payload = template.get("payload") if template and isinstance(template.get("payload"), list) else []
        if not payload:
            await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
            return

        first = payload[0]
        rest_pattern = first.get("rest_pattern") if isinstance(first.get("rest_pattern"), list) else []
        prefill_rest_pattern_minutes = [float(s or 0) / 60 for s in rest_pattern]
        exercise_name = "Упражнение"
        if first.get("exercise_id") is not None:
            try:
                exercise_name = str(db.get_exercise(int(first.get("exercise_id"))).get("display_name") or exercise_name)
            except Exception:
                pass

        await state.update_data(
            mode="pattern" if rest_pattern else "strength",
            exercise_id=first.get("exercise_id"),
            exercise_name=exercise_name,
            exercise_display_name=exercise_name,
            template_edit_index=0,
            template_edit_total=len(payload),
            template_edit_flow="apply_template",
            template_edit_payload=payload,
            prefill_weight=float(first.get("weight") or 0),
            prefill_reps=int(first.get("reps") or 0),
            prefill_sets=int(first.get("sets_count") or 0),
            prefill_rest_minutes=float(first.get("rest_seconds") or 0) / 60,
            prefill_rest_pattern_minutes=prefill_rest_pattern_minutes,
            prefill_rest_pattern_text=", ".join(f"{v:g}" for v in prefill_rest_pattern_minutes),
        )
        await state.set_state(QuickLogStates.enter_weight)
        await message.answer(_format_template_edit_intro(first, 1, len(payload), exercise_name))
        await message.answer(
            f"{texts.ENTER_WEIGHT}\nТекущее: {float(first.get('weight') or 0):g} кг. Введи новое или отправь '.' чтобы оставить как есть",
            reply_markup=back_cancel_kb(),
        )
    except Exception:
        log.exception("edit_template_before_apply failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(StateFilter(TemplateBrowseStates.browsing, TemplateBrowseStates.confirming, TemplateBrowseStates.confirming_apply), F.text == "↩️ Назад")
async def templates_back(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        templates = data.get("templates_list") or []
        if templates:
            await state.set_state(TemplateBrowseStates.browsing)
            await message.answer(texts.TEMPLATES_TITLE, reply_markup=templates_list_kb(templates))
            return
        await state.clear()
        await message.answer(texts.MENU, reply_markup=main_menu_kb())
    except Exception:
        log.exception("templates_back failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(StateFilter(TemplateBrowseStates.browsing, TemplateBrowseStates.confirming, TemplateBrowseStates.confirming_apply), F.text == "↩️ В меню")
async def templates_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(texts.MENU, reply_markup=main_menu_kb())
