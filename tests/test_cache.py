from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError

from bot.services.cache import Cache


async def test_cache_get_returns_none_on_miss():
    redis = AsyncMock()
    redis.get.return_value = None

    cache = Cache(redis)

    assert await cache.get("track:1") is None


async def test_cache_roundtrip_json():
    redis = AsyncMock()
    storage: dict[str, tuple[str, int]] = {}

    async def fake_set(key, value, ex):
        storage[key] = (value, ex)
        return True

    async def fake_get(key):
        record = storage.get(key)
        if record is None:
            return None
        return record[0]

    redis.set.side_effect = fake_set
    redis.get.side_effect = fake_get

    cache = Cache(redis)
    payload = {"title": "Bohemian Rhapsody", "year": 1975}

    await cache.set("track:456", payload, ttl_seconds=60)
    loaded = await cache.get("track:456")

    assert loaded == payload
    assert storage["track:456"][1] == 60


async def test_get_or_fetch_uses_cache_hit():
    redis = AsyncMock()
    redis.get.return_value = '{"title": "Cached"}'

    cache = Cache(redis)
    fetcher = AsyncMock(return_value={"title": "Fetched"})

    value = await cache.get_or_fetch("track:1", fetcher, ttl_seconds=60)

    assert value == {"title": "Cached"}
    fetcher.assert_not_awaited()


async def test_get_or_fetch_fetches_and_sets_on_miss():
    redis = AsyncMock()
    redis.get.return_value = None

    cache = Cache(redis)
    fetcher = AsyncMock(return_value={"title": "Fetched"})

    value = await cache.get_or_fetch("track:1", fetcher, ttl_seconds=60)

    assert value == {"title": "Fetched"}
    fetcher.assert_awaited_once()
    redis.set.assert_awaited_once()


async def test_get_or_fetch_falls_back_when_redis_fails():
    redis = AsyncMock()
    redis.get.side_effect = RedisError("boom")

    cache = Cache(redis)
    fetcher = AsyncMock(return_value={"title": "Fetched"})

    value = await cache.get_or_fetch("track:1", fetcher, ttl_seconds=60)

    assert value == {"title": "Fetched"}
    fetcher.assert_awaited_once()


async def test_cache_noop_when_redis_missing():
    cache = Cache(None)

    assert await cache.get("track:1") is None
    await cache.set("track:1", {"title": "x"}, ttl_seconds=60)


async def test_cache_get_returns_none_when_redis_fails():
    redis = AsyncMock()
    redis.get.side_effect = RedisError("boom")

    cache = Cache(redis)

    assert await cache.get("track:1") is None


async def test_cache_set_noops_when_redis_fails():
    redis = AsyncMock()
    redis.set.side_effect = RedisError("boom")

    cache = Cache(redis)

    await cache.set("track:1", {"title": "x"}, ttl_seconds=60)


async def test_get_or_fetch_falls_back_when_set_fails():
    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.side_effect = RedisError("boom")

    cache = Cache(redis)
    fetcher = AsyncMock(return_value={"title": "Fetched"})

    value = await cache.get_or_fetch("track:1", fetcher, ttl_seconds=60)

    assert value == {"title": "Fetched"}
    fetcher.assert_awaited_once()
