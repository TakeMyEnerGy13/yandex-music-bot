import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import InlineQuery

from bot.handlers.inline import on_inline_query


def _query(text: str) -> MagicMock:
    query = MagicMock(spec=InlineQuery)
    query.id = "qid"
    query.query = text
    query.answer = AsyncMock()
    query.bot = MagicMock()
    query.bot.get_me = AsyncMock(return_value=MagicMock(username="Yandex_botik_bot"))
    return query


@pytest.fixture
def deps():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    yandex = MagicMock()
    yandex.get_track = AsyncMock(
        return_value={
            "id": "456",
            "title": "BR",
            "artists": ["Queen"],
            "album_title": "ANO",
            "album_year": 1975,
            "duration_ms": 355_000,
            "genre": "rock",
            "cover_uri": "avatars.yandex.net/x/%%",
        }
    )
    return {"cache": cache, "yandex": yandex}


async def test_inline_track_returns_one_article(deps):
    query = _query("https://music.yandex.ru/album/123/track/456")

    await on_inline_query(query, **deps, inline_timeout=0.8)

    query.answer.assert_awaited_once()
    results = query.answer.call_args.kwargs["results"]
    assert len(results) == 1
    article = results[0]
    assert "BR" in article.title
    assert "Queen" in article.title
    button = article.reply_markup.inline_keyboard[0][0]
    assert button.url == "https://t.me/Yandex_botik_bot?start=similar_456"


async def test_inline_invalid_query_returns_hint(deps):
    query = _query("not a url")

    await on_inline_query(query, **deps, inline_timeout=0.8)

    query.answer.assert_awaited_once()
    kwargs = query.answer.call_args.kwargs
    assert kwargs["results"] == []
    assert kwargs["cache_time"] == 10
    assert kwargs["is_personal"] is True


async def test_inline_uses_cache_on_hit(deps):
    deps["cache"].get = AsyncMock(
        return_value={
            "track": {
                "id": "456",
                "title": "Cached",
                "artists": ["X"],
                "album_title": "A",
                "album_year": 2020,
                "duration_ms": 100_000,
                "genre": None,
                "cover_uri": "x/%%",
            },
            "songlinks": {},
        }
    )
    query = _query("https://music.yandex.ru/track/456")

    await on_inline_query(query, **deps, inline_timeout=0.8)

    deps["yandex"].get_track.assert_not_awaited()
    query.answer.assert_awaited_once()


async def test_inline_returns_empty_on_timeout(deps):
    async def slow(*args, **kwargs):
        await asyncio.sleep(2.0)
        return {}

    deps["yandex"].get_track = AsyncMock(side_effect=slow)
    query = _query("https://music.yandex.ru/track/456")

    await on_inline_query(query, **deps, inline_timeout=0.05)

    query.answer.assert_awaited_once()
    kwargs = query.answer.call_args.kwargs
    assert kwargs["results"] == []


async def test_inline_uses_injected_bot_username_without_get_me(deps):
    query = _query("https://music.yandex.ru/track/456")

    await on_inline_query(query, **deps, bot_username="InjectedBot", inline_timeout=0.8)

    query.bot.get_me.assert_not_awaited()
    results = query.answer.call_args.kwargs["results"]
    article = results[0]
    button = article.reply_markup.inline_keyboard[0][0]
    assert button.url == "https://t.me/InjectedBot?start=similar_456"
