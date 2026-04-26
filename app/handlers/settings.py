import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import texts
from app.config import is_admin as is_admin_by_env
from app.handlers.start import _parse_weight_kg
from app.keyboards import (
    body_weight_settings_kb,
    duration_kb,
    exercise_lang_kb,
    main_menu_kb,
    onboarding_weight_kb,
    settings_kb,
    train_freq_kb,
    translate_mode_kb,
    units_kb,
)
from app.states import SettingsStates

log = logging.getLogger("handlers.settings")
router = Router()

# Manual test-cases:
# 1) ⚙️ Настройки -> ⚖️ Вес тела -> enter "95" -> save and return to settings.
# 2) ⚙️ Настройки -> 📏 Рост/📅 Частота/⏱ Длительность -> save -> return to settings.
# 3) In weight edit press "⏭️ Пропустить" -> body_weight_kg becomes NULL and warning is shown.


async def _render_settings(message: Message, db) -> None:
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    units = user.get("units") or "kg"
    await message.answer(
        texts.SETTINGS_TEXT.format(units=units),
        reply_markup=settings_kb(is_admin=(db.is_admin(user) or is_admin_by_env(message.from_user.id))),
    )


@router.message(F.text == "⚖️ Вес тела")
async def open_body_weight_settings(message: Message, state: FSMContext, db):
    try:
        await state.set_state(SettingsStates.waiting_body_weight)
        await message.answer(texts.ONBOARDING_WEIGHT_PROMPT, reply_markup=body_weight_settings_kb())
    except Exception:
        log.exception("open_body_weight_settings failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.waiting_body_weight, F.text == "❌ Отмена")
async def cancel_edit_body_weight(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        await _render_settings(message, db)
    except Exception:
        log.exception("cancel_edit_body_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(
    SettingsStates.waiting_body_weight,
    F.text == "↩️ Назад",
)
@router.message(
    SettingsStates.waiting_height,
    F.text == "↩️ Назад",
)
@router.message(
    SettingsStates.waiting_train_freq,
    F.text == "↩️ Назад",
)
@router.message(
    SettingsStates.waiting_avg_duration,
    F.text == "↩️ Назад",
)
async def back_from_profile_edit(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        await _render_settings(message, db)
    except Exception:
        log.exception("back_from_profile_edit failed")
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
            await message.answer(texts.ERR_NUMBER + "\nДиапазон: 20..350 кг.", reply_markup=body_weight_settings_kb())
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.update_user_body_weight(user_id=int(user["id"]), body_weight_kg=weight)
        await state.clear()
        await message.answer(texts.SETTINGS_WEIGHT_UPDATED, reply_markup=main_menu_kb())
        await _render_settings(message, db)
    except Exception:
        log.exception("save_body_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "📏 Рост")
async def ask_height(message: Message, state: FSMContext):
    try:
        await state.set_state(SettingsStates.waiting_height)
        await message.answer(texts.SETTINGS_HEIGHT_PROMPT, reply_markup=onboarding_weight_kb())
    except Exception:
        log.exception("ask_height failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.waiting_height, F.text == "⏭️ Пропустить")
async def clear_height(message: Message, state: FSMContext, db):
    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.update_user_height(user_id=int(user["id"]), height_cm=None)
        await state.clear()
        await message.answer(texts.SETTINGS_HEIGHT_SKIPPED, reply_markup=main_menu_kb())
        await _render_settings(message, db)
    except Exception:
        log.exception("clear_height failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.waiting_height)
async def save_height(message: Message, state: FSMContext, db):
    try:
        value = (message.text or "").strip()
        if not value.isdigit():
            await message.answer(texts.SETTINGS_HEIGHT_INVALID, reply_markup=onboarding_weight_kb())
            return
        parsed = int(value)
        if parsed < 100 or parsed > 230:
            await message.answer(texts.SETTINGS_HEIGHT_INVALID, reply_markup=onboarding_weight_kb())
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.update_user_height(user_id=int(user["id"]), height_cm=parsed)
        await state.clear()
        await message.answer(texts.SETTINGS_HEIGHT_UPDATED, reply_markup=main_menu_kb())
        await _render_settings(message, db)
    except Exception:
        log.exception("save_height failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "📅 Частота")
async def ask_train_freq(message: Message, state: FSMContext):
    try:
        await state.set_state(SettingsStates.waiting_train_freq)
        await message.answer(texts.SETTINGS_FREQ_PROMPT, reply_markup=train_freq_kb())
    except Exception:
        log.exception("ask_train_freq failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.waiting_train_freq)
async def save_train_freq(message: Message, state: FSMContext, db):
    try:
        value = (message.text or "").strip()
        if not value.isdigit():
            await message.answer(texts.SETTINGS_FREQ_INVALID, reply_markup=train_freq_kb())
            return
        parsed = int(value)
        if parsed < 1 or parsed > 7:
            await message.answer(texts.SETTINGS_FREQ_INVALID, reply_markup=train_freq_kb())
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.update_user_freq(user_id=int(user["id"]), train_freq_per_week=parsed)
        await state.clear()
        await message.answer(texts.SETTINGS_FREQ_UPDATED, reply_markup=main_menu_kb())
        await _render_settings(message, db)
    except Exception:
        log.exception("save_train_freq failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "⏱ Длительность")
async def ask_avg_duration(message: Message, state: FSMContext):
    try:
        await state.set_state(SettingsStates.waiting_avg_duration)
        await message.answer(texts.SETTINGS_DURATION_PROMPT, reply_markup=duration_kb())
    except Exception:
        log.exception("ask_avg_duration failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SettingsStates.waiting_avg_duration)
async def save_avg_duration(message: Message, state: FSMContext, db):
    try:
        value = (message.text or "").strip()
        if not value.isdigit():
            await message.answer(texts.SETTINGS_DURATION_INVALID, reply_markup=duration_kb())
            return
        parsed = int(value)
        if parsed not in {25, 45, 60, 90, 120}:
            await message.answer(texts.SETTINGS_DURATION_INVALID, reply_markup=duration_kb())
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.update_user_duration(user_id=int(user["id"]), avg_duration_min=parsed)
        await state.clear()
        await message.answer(texts.SETTINGS_DURATION_UPDATED, reply_markup=main_menu_kb())
        await _render_settings(message, db)
    except Exception:
        log.exception("save_avg_duration failed")
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
