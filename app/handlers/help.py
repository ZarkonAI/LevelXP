import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import texts
from app.keyboards import help_inline_kb, main_menu_kb
from app.states import SupportStates

log = logging.getLogger("handlers.help")
router = Router()


def _normalize_username(message: Message) -> str:
    username = (message.from_user.username or "").strip()
    return f"@{username}" if username else "—"


def _format_ticket(kind: str, message: Message, text: str) -> str:
    return (
        f"🆕 Заявка: {kind}\n"
        f"От: {_normalize_username(message)} (tg_id={message.from_user.id})\n"
        f"Текст:\n{text.strip()}"
    )


@router.message(F.text == "❓ Помощь")
async def help_cmd(message: Message, state: FSMContext, support_username: str):
    try:
        await state.clear()
        await message.answer(texts.HELP_TEXT, reply_markup=help_inline_kb(support_username))
    except Exception:
        log.exception("help_cmd failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.callback_query(F.data == "support:write")
async def support_write_callback(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(SupportStates.waiting_text)
        await state.update_data(kind="support")
        if callback.message:
            await callback.message.answer(texts.SUPPORT_WRITE_PROMPT)
        await callback.answer()
    except Exception:
        log.exception("support_write_callback failed")
        await callback.answer(texts.TECH_ERROR, show_alert=True)


@router.callback_query(F.data == "support:exercise")
async def support_exercise_callback(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(SupportStates.waiting_text)
        await state.update_data(kind="exercise")
        if callback.message:
            await callback.message.answer(texts.SUPPORT_EXERCISE_PROMPT)
        await callback.answer()
    except Exception:
        log.exception("support_exercise_callback failed")
        await callback.answer(texts.TECH_ERROR, show_alert=True)


@router.callback_query(F.data == "help:back")
async def help_back_callback(callback: CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        if callback.message:
            await callback.message.delete()
            await callback.message.answer(texts.MENU, reply_markup=main_menu_kb())
        await callback.answer()
    except Exception:
        log.exception("help_back_callback failed")
        await callback.answer(texts.TECH_ERROR, show_alert=True)


@router.message(SupportStates.waiting_text, F.text)
async def support_text_received(message: Message, state: FSMContext, bot, admin_ids: tuple[int, ...]):
    try:
        text = (message.text or "").strip()
        if not text:
            await message.answer(texts.SUPPORT_EMPTY_TEXT)
            return

        data = await state.get_data()
        kind = str(data.get("kind") or "support")

        ticket_text = _format_ticket(kind, message, text)
        for admin_id in admin_ids:
            try:
                await bot.send_message(chat_id=admin_id, text=ticket_text)
            except Exception:
                log.exception("failed to deliver support ticket to admin_id=%s", admin_id)

        await message.answer(texts.SUPPORT_SENT, reply_markup=main_menu_kb())
        await state.clear()
    except Exception:
        log.exception("support_text_received failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(SupportStates.waiting_text)
async def support_waiting_non_text(message: Message):
    await message.answer(texts.SUPPORT_TEXT_ONLY)
