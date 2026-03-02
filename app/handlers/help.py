import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import texts
from app.keyboards import main_menu_kb

log = logging.getLogger("handlers.help")
router = Router()

@router.message(F.text == "❓ Помощь")
async def help_cmd(message: Message, state: FSMContext):
    try:
        await state.clear()
        text = ("Попытка сделать так, чтобы при нажатии на кнопку 'Помощь' открывалось сообщение с инструкцией по использованию бота. Если возникает ошибка, то отправляем сообщение об ошибке и возвращаемся в главное меню.")
        await message.answer(text, reply_markup=main_menu_kb())
    except Exception:
        log.exception("help_cmd failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())