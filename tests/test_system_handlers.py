from unittest.mock import AsyncMock, MagicMock

from aiogram.types import Message

from bot.handlers.system import cmd_help, cmd_ping, cmd_start


def _msg():
    message = MagicMock(spec=Message)
    message.text = "/start"
    message.answer = AsyncMock()
    message.bot = None
    return message


async def test_start_introduces_bot_and_mentions_inline():
    message = _msg()

    await cmd_start(message)

    text = message.answer.call_args.args[0]
    assert "Yandex.Music" in text or "Яндекс.Музык" in text
    assert "@" in text


async def test_help_lists_supported_link_types():
    message = _msg()

    await cmd_help(message)

    text = message.answer.call_args.args[0]
    for kind in ("track", "album", "playlist", "artist"):
        assert kind in text


async def test_ping_replies_pong():
    message = _msg()

    await cmd_ping(message)

    message.answer.assert_awaited_once_with("pong")


async def test_start_with_similar_payload_sends_similar_list():
    message = _msg()
    message.text = "/start similar_456"

    cache = MagicMock()
    cache.get = AsyncMock(
        side_effect=[
            {
                "track": {
                    "id": "456",
                    "title": "Source Track",
                    "artists": ["X"],
                    "album_title": "A",
                    "album_year": 2020,
                    "duration_ms": 100_000,
                    "genre": None,
                    "cover_uri": "x/%%",
                }
            },
            [{"id": "1", "title": "Sim 1", "artists": ["A"], "duration_ms": 100_000}],
        ]
    )
    cache.set = AsyncMock()

    yandex = MagicMock()
    yandex.get_track = AsyncMock()
    yandex.get_similar = AsyncMock()

    await cmd_start(message, cache=cache, yandex=yandex)

    message.answer.assert_awaited_once()
    text = message.answer.call_args.args[0]
    assert "Sim 1" in text
    yandex.get_track.assert_not_awaited()
