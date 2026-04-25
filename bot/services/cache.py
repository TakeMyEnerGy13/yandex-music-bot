import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)


class Cache:
    def __init__(self, redis: Redis | str | None):
        if isinstance(redis, str):
            self._redis = Redis.from_url(redis, decode_responses=True)
        else:
            self._redis = redis

    async def get(self, key: str) -> dict[str, Any] | None:
        if self._redis is None:
            return None

        try:
            raw = await self._redis.get(key)
        except RedisError:
            log.warning("cache get failed for %s", key, exc_info=True)
            return None
        if raw is None:
            return None

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        return json.loads(raw)

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        if self._redis is None:
            return

        payload = json.dumps(value, ensure_ascii=False)
        try:
            await self._redis.set(key, payload, ex=ttl_seconds)
        except RedisError:
            log.warning("cache set failed for %s", key, exc_info=True)

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[dict[str, Any]]],
        ttl_seconds: int,
    ) -> dict[str, Any]:
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = await fetcher()

        await self.set(key, value, ttl_seconds=ttl_seconds)

        return value

    async def close(self) -> None:
        if self._redis is None:
            return
        await self._redis.aclose()
