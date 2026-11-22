import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, ADMIN_IDS, DB_PATH, LOG_LEVEL
from database.db import Database
from services.ad_service import AdService
from handlers.user_handlers import register_handlers as register_user_handlers
from handlers.admin_handlers import register_admin_handlers as register_admin_handlers
from middlewares.subscription_middleware import SubscriptionMiddleware
from utils.logger import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging(LOG_LEVEL)
    logger.info("Запуск бота...")

    db = Database(DB_PATH)
    await db.init()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    ad_service = AdService(db, bot)

    # Регистрация middleware проверки подписки
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    # Регистрация хендлеров
    register_user_handlers(dp, db, ad_service)
    register_admin_handlers(dp, db, ad_service)

    # Сохраняем ссылки в боте для доступа из хендлеров (упрощённая передача)
    bot.db = db  # type: ignore[attr-defined]
    bot.ad_service = ad_service  # type: ignore[attr-defined]

    # Запускаем фоновую рассылку рекламы
    ad_service.start_broadcast()

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await ad_service.stop_broadcast()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")