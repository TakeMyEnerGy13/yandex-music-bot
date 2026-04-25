from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from bot.handlers.callbacks import on_similar, on_track_card


def _cb(data: str) -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.data = data
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.answer = AsyncMock()
    callback.message.answer_photo = AsyncMock()
    return callback


@pytest.fixture
def deps():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()

    yandex = MagicMock()
    yandex.get_track = AsyncMock(
        return_value={
            "id": "456",
            "title": "Source Track",
            "artists": ["X"],
            "album_title": "A",
            "album_year": 2020,
            "duration_ms": 200_000,
            "genre": None,
            "cover_uri": "x/%%",
        }
    )
    yandex.get_similar = AsyncMock(
        return_value=[
            {"id": "1", "title": "Sim 1", "artists": ["A"], "duration_ms": 100_000},
            {"id": "2", "title": "Sim 2", "artists": ["B"], "duration_ms": 120_000},
        ]
    )

    songlink = MagicMock()
    songlink.get_links = AsyncMock(return_value={})

    return {"cache": cache, "yandex": yandex, "songlink": songlink}


async def test_similar_callback_sends_text_list(deps):
    callback = _cb("similar:456")

    await on_similar(callback, **deps)

    deps["yandex"].get_similar.assert_awaited_once_with("456")
    callback.answer.assert_awaited_once()
    callback.message.answer.assert_awaited_once()
    text = callback.message.answer.call_args.args[0]
    assert "Sim 1" in text and "Sim 2" in text
    assert 'href="https://music.yandex.ru/track/1"' in text


async def test_similar_callback_uses_cache(deps):
    deps["cache"].get = AsyncMock(
        side_effect=[
            {
                "id": "456",
                "title": "Cached Source",
                "artists": ["X"],
                "album_title": "A",
                "album_year": 2020,
                "duration_ms": 100_000,
                "genre": None,
                "cover_uri": "x/%%",
            },
            [{"id": "9", "title": "C", "artists": ["Z"], "duration_ms": 90_000}],
        ]
    )
    callback = _cb("similar:456")

    await on_similar(callback, **deps)

    deps["yandex"].get_similar.assert_not_awaited()


async def test_track_card_drilldown_calls_get_track(deps):
    callback = _cb("track_card:9")

    await on_track_card(callback, **deps)

    deps["yandex"].get_track.assert_awaited_once_with("9")
    callback.answer.assert_awaited_once()
    callback.message.answer_photo.assert_awaited_once()
