import asyncio
import sys
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramNetworkError

from app.config import get_settings
from app.logging_setup import setup_logging
from app.db import Db
from app.handlers import all_routers

log = logging.getLogger("main")


async def run_polling(dp: Dispatcher, settings):
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        me = await bot.get_me()
        log.info("Authorized as @%s", me.username)

        await dp.start_polling(
            bot,
            db=dp["db"],
            admin_ids=settings.admin_ids,
            support_username=settings.support_username,
        )
    finally:
        await bot.session.close()


async def main():
    settings = get_settings()
    setup_logging(settings.log_level)

    dp = Dispatcher()

    db = Db(settings.supabase_url, settings.supabase_key)
    db.seed_exercises_if_empty()

    dp["db"] = db
    dp["admin_ids"] = settings.admin_ids
    dp["support_username"] = settings.support_username

    for r in all_routers:
        dp.include_router(r)

    log.info("Bot started")

    while True:
        try:
            log.info("Start polling")
            await run_polling(dp, settings)
        except (TelegramNetworkError, OSError) as e:
            log.exception("Polling crashed because of network error: %s", e)
            await asyncio.sleep(5)


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())