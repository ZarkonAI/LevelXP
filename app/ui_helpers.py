import logging
from typing import Optional

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

log = logging.getLogger("ui_helpers")


async def send_or_replace_work_message(
    source: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    inline_keyboard: Optional[InlineKeyboardMarkup] = None,
) -> int:
    data = await state.get_data()
    work_message_id = data.get("work_message_id")
    chat_id = data.get("work_chat_id")

    if isinstance(source, CallbackQuery) and source.message:
        chat_id = source.message.chat.id
    elif isinstance(source, Message):
        chat_id = source.chat.id

    if work_message_id and chat_id:
        try:
            bot = source.bot
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(work_message_id),
                text=text,
                reply_markup=inline_keyboard,
            )
            return int(work_message_id)
        except Exception:
            log.exception("send_or_replace_work_message edit failed")

    try:
        if isinstance(source, CallbackQuery) and source.message:
            sent = await source.message.answer(text, reply_markup=inline_keyboard)
        else:
            sent = await source.answer(text, reply_markup=inline_keyboard)
        await state.update_data(work_message_id=sent.message_id, work_chat_id=sent.chat.id)
        return int(sent.message_id)
    except Exception:
        log.exception("send_or_replace_work_message send failed")
        raise
