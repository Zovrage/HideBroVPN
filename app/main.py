from __future__ import annotations

import asyncio
import logging

import redis.asyncio as redis
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions
from aiogram.fsm.storage.redis import RedisStorage

from app.bot.handlers import admin as admin_handlers
from app.bot.handlers import user as user_handlers
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import Database
from app.services.business import BusinessService
from app.services.payments import MockGateway, YooKassaGateway
from app.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    db = Database(settings.postgres_dsn)

    redis_client = redis.from_url(settings.redis_dsn)
    storage = RedisStorage(redis_client)

    remnawave = RemnawaveClient(
        base_url=settings.remnawave_base_url,
        timeout_sec=settings.remnawave_timeout_sec,
        api_token=settings.remnawave_api_token,
        admin_username=settings.remnawave_admin_username,
        admin_password=settings.remnawave_admin_password,
        username_prefix=settings.username_prefix,
        username_min_digits=settings.username_min_digits,
        username_max_digits=settings.username_max_digits,
        internal_squad_uuid=settings.remnawave_internal_squad_uuid,
        device_limit=settings.device_limit,
    )
    await remnawave.ensure_ready()

    if settings.payments_provider == "yookassa":
        payments = YooKassaGateway(
            shop_id=settings.yookassa_shop_id,
            secret_key=settings.yookassa_secret_key,
            return_url=settings.yookassa_return_url,
        )
    else:
        payments = MockGateway()

    business = BusinessService(
        session_factory=db.session_factory,
        remnawave=remnawave,
        payments=payments,
        settings=settings,
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview=LinkPreviewOptions(is_disabled=True),
        ),
    )

    me = await bot.get_me()
    if not me.username:
        raise RuntimeError("У бота должен быть установлен username в Telegram")

    dp = Dispatcher(storage=storage)
    dp.include_router(user_handlers.router)
    dp.include_router(admin_handlers.router)

    dp["settings"] = settings
    dp["business"] = business
    dp["bot_username"] = me.username

    try:
        logger.info("Bot %s started", me.username)
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await remnawave.close()
        await payments.close()
        await db.dispose()
        await storage.close()
        await redis_client.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
