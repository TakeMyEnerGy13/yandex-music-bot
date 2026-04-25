import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import Settings
from bot.handlers import callbacks as callbacks_handler
from bot.handlers import inline as inline_handler
from bot.handlers import link as link_handler
from bot.handlers import system
from bot.middlewares import ErrorMiddleware, RateLimitMiddleware
from bot.services.cache import Cache
from bot.services.songlink import SongLinkClient
from bot.services.yandex import YandexMusicClient

log = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def main() -> None:
    settings = Settings()
    _setup_logging(settings.log_level)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    me = await bot.get_me()
    dp = Dispatcher()
    dp.message.middleware(ErrorMiddleware())
    dp.message.middleware(RateLimitMiddleware(per_minute=settings.rate_limit_per_minute))
    dp.callback_query.middleware(ErrorMiddleware())

    cache = Cache(settings.redis_url)
    yandex = YandexMusicClient(settings.yandex_music_token)
    songlink = SongLinkClient(timeout=settings.songlink_timeout)

    dp["cache"] = cache
    dp["yandex"] = yandex
    dp["songlink"] = songlink
    dp["settings"] = settings
    dp["bot_username"] = me.username
    dp["inline_timeout"] = settings.inline_timeout

    dp.include_router(system.router)
    dp.include_router(link_handler.router)
    dp.include_router(callbacks_handler.router)
    dp.include_router(inline_handler.router)

    log.info("bot starting (polling mode)")
    try:
        await dp.start_polling(bot)
    finally:
        await songlink.close()
        await cache.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
