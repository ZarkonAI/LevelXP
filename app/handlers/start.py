import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import texts
from app.keyboards import main_menu_kb, onboarding_height_kb, onboarding_weight_kb
from app.states import OnboardingStates

log = logging.getLogger("handlers.start")
router = Router()

# Manual test-cases:
# 1) /start with body_weight_kg=NULL -> question about weight appears.
# 2) Enter "80,5" -> saved, then height question appears; enter "175" -> menu opens.
# 3) Press "⏭️ Пропустить" on weight -> warning appears, then height step.
# 4) Press "↩️ Назад" on height -> returns to weight step.
# 5) /menu with body_weight_kg=NULL and no FSM state -> onboarding starts instead of regular menu.


def _parse_weight_kg(raw_value: str):
    value = (raw_value or "").strip().replace(",", ".")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not (20 <= parsed <= 350):
        return None
    return round(parsed, 2)


def _parse_height_cm(raw_value: str):
    value = (raw_value or "").strip()
    if not value.isdigit():
        return None
    parsed = int(value)
    if not (100 <= parsed <= 230):
        return None
    return parsed


async def _show_main_menu(message: Message) -> None:
    await message.answer(texts.MENU, reply_markup=main_menu_kb())


async def _start_onboarding(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.waiting_body_weight)
    await message.answer(texts.ONBOARDING_WEIGHT_PROMPT, reply_markup=onboarding_weight_kb())


async def _ensure_onboarding_or_menu(message: Message, state: FSMContext, db) -> None:
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    db.ensure_progress(user["id"])
    if user.get("body_weight_kg") is None:
        await _start_onboarding(message, state)
        return
    await _show_main_menu(message)


@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext, db):
    try:
        await state.clear()
        await message.answer(texts.START, reply_markup=main_menu_kb())
        await _ensure_onboarding_or_menu(message, state, db)
    except Exception:
        log.exception("start failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(Command("menu"), StateFilter(None))
async def menu_cmd_with_onboarding(message: Message, state: FSMContext, db):
    try:
        await _ensure_onboarding_or_menu(message, state, db)
    except Exception:
        log.exception("menu_cmd_with_onboarding failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(F.text == "↩️ В меню", StateFilter(None))
async def back_to_menu_with_onboarding(message: Message, state: FSMContext, db):
    try:
        await _ensure_onboarding_or_menu(message, state, db)
    except Exception:
        log.exception("back_to_menu_with_onboarding failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(OnboardingStates.waiting_body_weight, F.text == "❌ Отмена")
async def onboarding_cancel_on_weight(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(texts.CANCELLED, reply_markup=main_menu_kb())


@router.message(OnboardingStates.waiting_body_weight, F.text == "⏭️ Пропустить")
async def onboarding_skip_weight(message: Message, state: FSMContext, db):
    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.set_body_weight(user_id=int(user["id"]), kg=None)
        await state.set_state(OnboardingStates.waiting_height)
        await message.answer(texts.ONBOARDING_WEIGHT_WARNING, reply_markup=onboarding_height_kb())
        await message.answer(texts.ONBOARDING_HEIGHT_PROMPT, reply_markup=onboarding_height_kb())
    except Exception:
        log.exception("onboarding_skip_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(OnboardingStates.waiting_body_weight)
async def onboarding_save_weight(message: Message, state: FSMContext, db):
    try:
        weight = _parse_weight_kg(message.text or "")
        if weight is None:
            await message.answer(texts.ERR_NUMBER + "\nДиапазон: 20..350 кг.", reply_markup=onboarding_weight_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.set_body_weight(user_id=int(user["id"]), kg=weight)
        await state.set_state(OnboardingStates.waiting_height)
        await message.answer(texts.ONBOARDING_HEIGHT_PROMPT, reply_markup=onboarding_height_kb())
    except Exception:
        log.exception("onboarding_save_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(OnboardingStates.waiting_height, F.text == "❌ Отмена")
async def onboarding_cancel_on_height(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(texts.CANCELLED, reply_markup=main_menu_kb())


@router.message(OnboardingStates.waiting_height, F.text == "↩️ Назад")
async def onboarding_back_to_weight(message: Message, state: FSMContext):
    await state.set_state(OnboardingStates.waiting_body_weight)
    await message.answer(texts.ONBOARDING_WEIGHT_PROMPT, reply_markup=onboarding_weight_kb())


@router.message(OnboardingStates.waiting_height, F.text == "⏭️ Пропустить")
async def onboarding_skip_height(message: Message, state: FSMContext, db):
    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.set_height(user_id=int(user["id"]), cm=None)
        await state.clear()
        await message.answer(texts.ONBOARDING_DONE, reply_markup=main_menu_kb())
        await _show_main_menu(message)
    except Exception:
        log.exception("onboarding_skip_height failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(OnboardingStates.waiting_height)
async def onboarding_save_height(message: Message, state: FSMContext, db):
    try:
        height = _parse_height_cm(message.text or "")
        if height is None:
            await message.answer("Введи целое число от 100 до 230.", reply_markup=onboarding_height_kb())
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.set_height(user_id=int(user["id"]), cm=height)
        await state.clear()
        await message.answer(texts.ONBOARDING_DONE, reply_markup=main_menu_kb())
        await _show_main_menu(message)
    except Exception:
        log.exception("onboarding_save_height failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(Command("ping"))
async def ping(message: Message):
    await message.answer(texts.PING, reply_markup=main_menu_kb())


@router.message(Command("version"))
async def version(message: Message):
    await message.answer(texts.VERSION, reply_markup=main_menu_kb())
