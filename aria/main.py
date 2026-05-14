"""
Aria salon bot — entry point.

Usage:
    python -m aria.main
or
    python aria/main.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from aria.config import settings
from aria.db.repo import init_db, close_pool
from aria.handlers.start import router as start_router
from aria.handlers.chat import router as chat_router
from aria.services.scheduler import get_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("aria")


async def on_startup(bot: Bot) -> None:
    await init_db(settings.DATABASE_URL)
    get_scheduler().start()
    me = await bot.get_me()
    log.info("Aria bot @%s is running", me.username)


async def on_shutdown(bot: Bot) -> None:
    get_scheduler().shutdown(wait=False)
    await close_pool()
    log.info("Aria bot shut down cleanly")


async def main() -> None:
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Order matters — start/help/reset before the catch-all chat handler
    dp.include_router(start_router)
    dp.include_router(chat_router)

    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
