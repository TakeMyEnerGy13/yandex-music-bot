import logging
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

log = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, per_minute: int = 10):
        self._limit = per_minute
        self._window = 60.0
        self._buckets: dict[int, deque[float]] = defaultdict(deque)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        now = time.monotonic()
        bucket = self._buckets[user.id]
        while bucket and now - bucket[0] > self._window:
            bucket.popleft()

        if len(bucket) >= self._limit:
            if hasattr(event, "answer"):
                await event.answer("🐢 Слишком быстро, подожди немного.")
            return None

        bucket.append(now)
        return await handler(event, data)


class ErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            log.exception("unhandled error in handler")
            if hasattr(event, "answer"):
                try:
                    await event.answer("⚠️ Что-то пошло не так. Уже разбираемся.")
                except Exception:
                    log.exception("failed to send error message")
            return None
