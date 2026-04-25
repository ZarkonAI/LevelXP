import logging
import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import texts
from app.config import is_admin as is_admin_by_env
from app.handlers.start import _parse_weight_kg
from app.keyboards import (
    body_weight_settings_kb,
    exercise_lang_kb,
    main_menu_kb,
    onboarding_weight_kb,
    settings_kb,
    translate_mode_kb,
    units_kb,
)
from app.states import SettingsStates

log = logging.getLogger("handlers.settings")
router = Router()
TZ_RE = re.compile(r"^UTC[+-]\d{1,2}$")

# Manual test-cases:
# 1) ⚙️ Настройки -> ⚖️ Вес тела shows current value or "не указан".
# 2) ⚖️ Вес тела -> ✏️ Изменить -> enter "95" -> save and return to settings.
# 3) In weight edit press "⏭️ Пропустить" -> body_weight_kg becomes NULL and warning is shown.


async def _render_settings(message: Message, db) -> None:
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    units = user.get("units") or "kg"
    timezone_value = user.get("timezone") or "UTC+0"
    await message.answer(
        texts.SETTINGS_TEXT.format(units=units, timezone=timezone_value),
        reply_markup=settings_kb(is_admin=(db.is_admin(user) or is_admin_by_env(message.from_user.id))),
    )


@router.message(F.text == "⚖️ Вес тела")
async def open_body_weight_settings(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        current = db.get_body_weight(user_id=int(user["id"]))
        value = texts.SETTINGS_WEIGHT_EMPTY if current is None else f"{current:g} кг"
        await message.answer(
            texts.SETTINGS_WEIGHT_TITLE.format(value=value),
            reply_markup=body_weight_settings_kb(),
        )
    except Exception:
        log.exception("open_body_weight_settings failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "✏️ Изменить")
async def edit_body_weight(message: Message, state: FSMContext):
    try:
        await state.set_state(SettingsStates.waiting_body_weight)
        await message.answer(texts.ONBOARDING_WEIGHT_PROMPT, reply_markup=onboarding_weight_kb())
    except Exception:
        log.exception("edit_body_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.waiting_body_weight, F.text == "❌ Отмена")
async def cancel_edit_body_weight(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        await _render_settings(message, db)
    except Exception:
        log.exception("cancel_edit_body_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.waiting_body_weight, F.text == "⏭️ Пропустить")
async def clear_body_weight(message: Message, state: FSMContext, db):
    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.set_body_weight(user_id=int(user["id"]), kg=None)
        await state.clear()
        await message.answer(texts.ONBOARDING_WEIGHT_WARNING, reply_markup=main_menu_kb())
        await _render_settings(message, db)
    except Exception:
        log.exception("clear_body_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.waiting_body_weight)
async def save_body_weight(message: Message, state: FSMContext, db):
    try:
        weight = _parse_weight_kg(message.text or "")
        if weight is None:
            await message.answer(texts.ERR_NUMBER + "\nДиапазон: 20..350 кг.", reply_markup=onboarding_weight_kb())
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.set_body_weight(user_id=int(user["id"]), kg=weight)
        await state.clear()
        await message.answer(texts.SETTINGS_WEIGHT_UPDATED, reply_markup=main_menu_kb())
        await _render_settings(message, db)
    except Exception:
        log.exception("save_body_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "🌐 Язык упражнений")
async def choose_exercise_lang(message: Message, state: FSMContext):
    try:
        await state.set_state(SettingsStates.exercise_lang_menu)
        await message.answer(texts.SETTINGS_EXERCISE_LANG_PROMPT, reply_markup=exercise_lang_kb())
    except Exception:
        log.exception("choose_exercise_lang failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.exercise_lang_menu, F.text == "↩️ Назад")
async def back_from_exercise_lang(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        await _render_settings(message, db)
    except Exception:
        log.exception("back_from_exercise_lang failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.exercise_lang_menu, F.text.in_({"Русский (если есть)", "English"}))
async def set_exercise_lang(message: Message, state: FSMContext, db):
    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        lang = "ru" if message.text == "Русский (если есть)" else "en"
        db.set_exercise_lang(user_id=int(user["id"]), lang=lang)
        await state.clear()
        await _render_settings(message, db)
    except Exception:
        log.exception("set_exercise_lang failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "✍️ Режим перевода")
async def choose_translate_mode(message: Message, state: FSMContext, db):
    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        if not db.is_admin(user):
            await message.answer(texts.UNAVAILABLE, reply_markup=settings_kb(is_admin=False))
            return
        await state.set_state(SettingsStates.translate_mode_menu)
        await message.answer(texts.SETTINGS_TRANSLATE_MODE_PROMPT, reply_markup=translate_mode_kb())
    except Exception:
        log.exception("choose_translate_mode failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.translate_mode_menu, F.text == "↩️ Назад")
async def back_from_translate_mode(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        await _render_settings(message, db)
    except Exception:
        log.exception("back_from_translate_mode failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.translate_mode_menu, F.text.in_({"Вкл", "Выкл"}))
async def set_translate_mode(message: Message, state: FSMContext, db):
    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        if not db.is_admin(user):
            await state.clear()
            await message.answer(texts.UNAVAILABLE, reply_markup=settings_kb(is_admin=False))
            return
        db.set_translate_mode(user_id=int(user["id"]), enabled=message.text == "Вкл")
        await state.clear()
        await _render_settings(message, db)
    except Exception:
        log.exception("set_translate_mode failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "⚙️ Настройки")
async def open_settings(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        await _render_settings(message, db)
    except Exception:
        log.exception("open_settings failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "⚖️ Единицы")
async def choose_units(message: Message, state: FSMContext):
    try:
        await state.set_state(SettingsStates.units_menu)
        await message.answer(texts.SETTINGS_UNITS_PROMPT, reply_markup=units_kb())
    except Exception:
        log.exception("choose_units failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.units_menu, F.text == "↩️ Назад")
async def back_to_settings(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        await _render_settings(message, db)
    except Exception:
        log.exception("back_to_settings failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text.in_({"kg", "lb"}))
async def set_units(message: Message, state: FSMContext, db):
    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.update_user_units(user_id=int(user["id"]), units=message.text)
        await state.clear()
        await _render_settings(message, db)
    except Exception:
        log.exception("set_units failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "🕒 Часовой пояс")
async def ask_timezone(message: Message, state: FSMContext):
    try:
        await state.set_state(SettingsStates.waiting_timezone)
        await message.answer(texts.SETTINGS_TIMEZONE_PROMPT, reply_markup=main_menu_kb())
    except Exception:
        log.exception("ask_timezone failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(StateFilter(SettingsStates.waiting_timezone))
async def save_timezone(message: Message, state: FSMContext, db):
    try:
        value = (message.text or "").strip()
        if not TZ_RE.fullmatch(value):
            await message.answer(texts.SETTINGS_TIMEZONE_INVALID, reply_markup=main_menu_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.update_user_timezone(user_id=int(user["id"]), timezone_value=value)
        await state.clear()
        await _render_settings(message, db)
    except Exception:
        log.exception("save_timezone failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
