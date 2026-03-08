import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.config import get_settings
from app.logging_setup import setup_logging
from app.db import Db
from app.handlers import all_routers

log = logging.getLogger("main")

async def main():
    settings = get_settings()
    setup_logging(settings.log_level)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    db = Db(settings.supabase_url, settings.supabase_key)
    db.seed_exercises_if_empty()

    # простой dependency injection через data
    dp["db"] = db
    dp["admin_ids"] = settings.admin_ids

    for r in all_routers:
        dp.include_router(r)

    log.info("Bot started")
    log.info("Start polling")
    await dp.start_polling(bot, db=db, admin_ids=settings.admin_ids)

if __name__ == "__main__":
    asyncio.run(main())