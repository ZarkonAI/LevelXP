import logging
import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import db as db_module
from app import texts
from app.keyboards import (
    back_cancel_kb,
    main_menu_kb,
    templates_confirm_inline_kb,
    templates_confirm_kb,
    templates_list_inline_kb,
    templates_list_kb,
)
from app.states import QuickLogStates, TemplateBrowseStates
from app.ui_helpers import send_or_replace_work_message

log = logging.getLogger("handlers.templates")
router = Router()
INDEX_RE = re.compile(r"^(\d+)\)")
MUSCLE_LABELS = {"legs": "🦵 Ноги", "core": "🎯 Кор", "back": "🧱 Спина", "chest": "🫀 Грудь", "shoulders": "🧍 Плечи", "arms": "💪 Руки"}


def _format_payload(payload: list[dict], db) -> str:
    if not payload:
        return "• пустой шаблон"
    lines = []
    for idx, item in enumerate(payload, start=1):
        ex_name = "Упражнение"
        ex_id = item.get("exercise_id")
        if ex_id is not None:
            try:
                ex_name = str(db.get_exercise(int(ex_id)).get("name") or ex_name)
            except Exception:
                pass
        lines.append(f"{idx}. {ex_name} — {float(item.get('weight') or 0):g}кг × {int(item.get('reps') or 0)} × {int(item.get('sets_count') or 0)}")
    return "\n".join(lines)


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


async def _show_template_card_compact(source: Message | CallbackQuery, state: FSMContext, db, user_id: int, template_id: int):
    template = db.get_template(user_id=user_id, template_id=template_id)
    if not template:
        await send_or_replace_work_message(source, state, texts.TECH_ERROR)
        return
    payload = template.get("payload") if isinstance(template.get("payload"), list) else []
    await state.update_data(selected_template_id=template_id)
    await state.set_state(TemplateBrowseStates.confirming)
    await send_or_replace_work_message(
        source,
        state,
        f"<b>{template.get('name', 'Шаблон')}</b>\n\n{_format_payload(payload, db)}",
        templates_confirm_inline_kb(template_id),
    )


async def _is_compact_mode(message: Message, db) -> bool:
    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        return db.get_user_ui_mode(int(user["id"])) == "compact"
    except Exception:
        log.exception("templates _is_compact_mode failed")
        return False


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
        if await _is_compact_mode(message, db):
            await send_or_replace_work_message(message, state, texts.TEMPLATES_TITLE, templates_list_inline_kb(templates))
        else:
            await message.answer(texts.TEMPLATES_TITLE, reply_markup=templates_list_kb(templates))
    except Exception:
        log.exception("open_templates failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.callback_query(F.data.startswith("templates:"))
async def templates_compact_callbacks(callback: CallbackQuery, state: FSMContext, db):
    try:
        user = db.get_or_create_user(callback.from_user.id, callback.from_user.username)
        if db.get_user_ui_mode(int(user["id"])) != "compact":
            await callback.answer()
            return

        parts = (callback.data or "").split(":")
        action = parts[1] if len(parts) > 1 else ""
        template_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        state_data = await state.get_data()
        templates = state_data.get("templates_list") or db.list_templates(user_id=int(user["id"]))

        if action == "open" and template_id:
            await _show_template_card_compact(callback, state, db, user_id=int(user["id"]), template_id=template_id)
        elif action == "back":
            await state.set_state(TemplateBrowseStates.browsing)
            await send_or_replace_work_message(callback, state, texts.TEMPLATES_TITLE, templates_list_inline_kb(templates))
        elif action == "apply" and template_id:
            await state.update_data(selected_template_id=template_id)
            await apply_template(callback.message, state, db)
        elif action == "edit" and template_id:
            await state.update_data(selected_template_id=template_id)
            await edit_template_before_apply(callback.message, state, db)
        await callback.answer()
    except Exception:
        log.exception("templates_compact_callbacks failed")
        await callback.answer()


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

        total_xp = 0
        total_sets = 0
        muscle_delta = {}
        top = []
        for item in payload:
            ex_id = item.get("exercise_id")
            if ex_id is None:
                continue
            award = db.award_and_update_progress(
                user_id=int(user["id"]),
                exercise_id=int(ex_id),
                weight=float(item.get("weight") or 0),
                reps=int(item.get("reps") or 0),
                sets_count=int(item.get("sets_count") or 0),
            )
            total_xp += int(award.get("xp_gain") or 0)
            total_sets += int(award.get("total_sets_for_workout") or 0)
            for m, val in (award.get("muscle_delta") or {}).items():
                muscle_delta[m] = int(muscle_delta.get(m, 0)) + int(val)
            top.extend(award.get("muscle_gains_sorted_top3") or [])

        db.update_workout_metrics(int(user["id"]), int(workout_id), total_xp=total_xp, total_sets=total_sets, muscle_delta=muscle_delta, status="done")
        progress = db.get_progress(int(user["id"]))
        reward_text = (
            "<b>LevelXP · Награда</b>\n"
            f"+<b>{total_xp} XP</b> | Уровень: <b>{progress['level']}</b>\n"
            f"XP: <b>{progress['xp']}/{100 + int(progress['level']) * 25}</b>\n\n"
            "<b>Прокачка</b>\n"
            + ("\n".join([f"- {MUSCLE_LABELS.get(m, '🏋️ Нагрузка')}: +{g}" for m, g in top[:3]]) if top else "- 🏋️ Общая нагрузка учтена")
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
        await state.update_data(
            mode="pattern" if rest_pattern else "strength",
            exercise_id=first.get("exercise_id"),
            exercise_name="Упражнение",
            template_edit_payload=payload,
            prefill_weight=float(first.get("weight") or 0),
            prefill_reps=int(first.get("reps") or 0),
            prefill_sets=int(first.get("sets_count") or 0),
            prefill_rest_minutes=float(first.get("rest_seconds") or 0) / 60,
            prefill_rest_pattern_minutes=prefill_rest_pattern_minutes,
            prefill_rest_pattern_text=", ".join(f"{v:g}" for v in prefill_rest_pattern_minutes),
        )
        await state.set_state(QuickLogStates.enter_weight)
        await message.answer(f"{texts.ENTER_WEIGHT}\nТекущее: {float(first.get('weight') or 0):g} кг. Введи новое или отправь '.' чтобы оставить как есть", reply_markup=back_cancel_kb())
    except Exception:
        log.exception("edit_template_before_apply failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(StateFilter(TemplateBrowseStates.browsing, TemplateBrowseStates.confirming), F.text == "↩️ Назад")
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


@router.message(StateFilter(TemplateBrowseStates.browsing, TemplateBrowseStates.confirming), F.text == "↩️ В меню")
async def templates_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(texts.MENU, reply_markup=main_menu_kb())
