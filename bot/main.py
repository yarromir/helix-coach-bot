"""точка входа: инициализация бота, бд, планировщика и роутеров."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import config
from bot.database.db import Database
from bot.handlers import analytics, common, export, nutrition, settings, start, workout
from bot.handlers.reminders import schedule_all

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="онбординг / меню"),
    BotCommand(command="программа", description="текущая программа"),
    BotCommand(command="тренировка", description="записать тренировку"),
    BotCommand(command="техника", description="разбор техники"),
    BotCommand(command="замеры", description="вес/замеры/самочувствие"),
    BotCommand(command="прогресс", description="графики прогресса"),
    BotCommand(command="питание", description="учёт еды и калорий"),
    BotCommand(command="меню", description="меню на день"),
    BotCommand(command="продукт", description="добавить свой продукт"),
    BotCommand(command="анализы", description="анализы helix"),
    BotCommand(command="история", description="история анализов"),
    BotCommand(command="коррекция", description="перестроить программу"),
    BotCommand(command="настройки", description="настройки"),
    BotCommand(command="экспорт", description="выгрузка csv"),
    BotCommand(command="помощь", description="список команд"),
    BotCommand(command="стоп", description="отменить операцию"),
]


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def main() -> None:
    setup_logging()
    config.validate()

    db = Database(config.db_path)
    await db.connect()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=None))
    scheduler = AsyncIOScheduler(timezone=config.default_tz)

    dp = Dispatcher()
    dp.include_router(common.router)          # /стоп, /помощь — приоритетно
    dp.include_router(start.router)
    dp.include_router(workout.router)
    dp.include_router(nutrition.router)
    dp.include_router(analytics.router)
    dp.include_router(settings.router)
    dp.include_router(export.router)
    dp.include_router(common.fallback_router)  # подключается последним

    scheduler.start()
    await schedule_all(scheduler, bot, db)
    await bot.set_my_commands(COMMANDS)

    logger.info("бот запущен")
    try:
        await dp.start_polling(bot, db=db, scheduler=scheduler)
    finally:
        scheduler.shutdown(wait=False)
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
