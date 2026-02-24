import logging
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from app.keyboards import main_menu_kb
from app import texts

log = logging.getLogger("handlers.start")
router = Router()

@router.message(CommandStart())
async def start_cmd(message: Message, db):
    try:
        tg_id = message.from_user.id
        username = message.from_user.username
        user = db.get_or_create_user(tg_id, username)
        db.ensure_progress(user["id"])

        await message.answer(texts.START, reply_markup=main_menu_kb())
        await message.answer(texts.MENU, reply_markup=main_menu_kb())
    except Exception:
        log.exception("start failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())

@router.message(Command("ping"))
async def ping(message: Message):
    await message.answer(texts.PING, reply_markup=main_menu_kb())