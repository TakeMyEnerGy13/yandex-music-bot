from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from bot.handlers.link import handle_link


def _msg(text: str) -> MagicMock:
    message = MagicMock(spec=Message)
    message.text = text
    message.answer = AsyncMock()
    message.answer_photo = AsyncMock()
    return message


@pytest.fixture
def deps():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()

    yandex = MagicMock()
    yandex.get_track = AsyncMock(
        return_value={
            "id": "456",
            "title": "Bohemian Rhapsody",
            "artists": ["Queen"],
            "album_id": "123",
            "album_title": "A Night at the Opera",
            "album_year": 1975,
            "duration_ms": 355_000,
            "genre": "rock",
            "cover_uri": "avatars.yandex.net/x/%%",
        }
    )
    yandex.get_album = AsyncMock()
    yandex.get_artist = AsyncMock()
    yandex.get_playlist = AsyncMock()
    yandex.get_playlist_by_uuid = AsyncMock()

    songlink = MagicMock()
    songlink.get_links = AsyncMock(return_value={"Spotify": "https://open.spotify.com/track/x"})

    return {"cache": cache, "yandex": yandex, "songlink": songlink}


async def test_track_link_sends_photo_with_caption(deps):
    message = _msg("https://music.yandex.ru/album/123/track/456")

    await handle_link(message, **deps)

    deps["yandex"].get_track.assert_awaited_once_with("456")
    deps["songlink"].get_links.assert_awaited_once_with("https://music.yandex.ru/album/123/track/456")
    message.answer_photo.assert_awaited_once()
    kwargs = message.answer_photo.call_args.kwargs
    assert "Bohemian Rhapsody" in kwargs["caption"]
    assert "Spotify" in kwargs["caption"]
    assert kwargs["reply_markup"] is not None


async def test_track_link_uses_cache_on_hit(deps):
    deps["cache"].get = AsyncMock(
        return_value={
            "track": {
                "id": "456",
                "title": "Cached",
                "artists": ["X"],
                "album_id": "123",
                "album_title": "A",
                "album_year": 2020,
                "duration_ms": 100_000,
                "genre": None,
                "cover_uri": "x/%%",
            },
            "songlinks": {"Spotify": "https://x"},
        }
    )
    message = _msg("https://music.yandex.ru/track/456")

    await handle_link(message, **deps)

    deps["yandex"].get_track.assert_not_awaited()
    deps["songlink"].get_links.assert_not_awaited()
    message.answer_photo.assert_awaited_once()


async def test_track_short_link_uses_album_id_from_yandex_for_songlink(deps):
    message = _msg("https://music.yandex.ru/track/456")

    await handle_link(message, **deps)

    deps["songlink"].get_links.assert_awaited_once_with("https://music.yandex.ru/album/123/track/456")


async def test_unknown_link_replies_friendly_error(deps):
    message = _msg("https://example.com/whatever")

    await handle_link(message, **deps)

    message.answer.assert_awaited_once()
    assert "не похоже" in message.answer.call_args.args[0].lower() or "поддерж" in message.answer.call_args.args[0].lower()
    message.answer_photo.assert_not_awaited()


async def test_album_link_routes_to_album(deps):
    deps["yandex"].get_album = AsyncMock(
        return_value={
            "id": "123",
            "title": "X",
            "artists": ["Y"],
            "year": 2020,
            "track_count": 1,
            "duration_ms": 60_000,
            "cover_uri": "x/%%",
            "tracks": [{"title": "t", "duration_ms": 60_000}],
        }
    )
    message = _msg("https://music.yandex.ru/album/123")

    await handle_link(message, **deps)

    deps["yandex"].get_album.assert_awaited_once_with("123")
    message.answer_photo.assert_awaited_once()


async def test_artist_link_routes_to_artist(deps):
    deps["yandex"].get_artist = AsyncMock(
        return_value={
            "id": "789",
            "name": "Queen",
            "cover_uri": "x/%%",
            "top_tracks": [{"id": "1", "title": "BR", "duration_ms": 355_000}],
        }
    )
    message = _msg("https://music.yandex.ru/artist/789")

    await handle_link(message, **deps)

    deps["yandex"].get_artist.assert_awaited_once_with("789")


async def test_playlist_link_routes_to_playlist(deps):
    deps["yandex"].get_playlist = AsyncMock(
        return_value={
            "id": "1001",
            "owner": "myname",
            "title": "Mix",
            "track_count": 1,
            "duration_ms": 60_000,
            "cover_uri": "x/%%",
            "tracks": [{"title": "s", "artists": ["a"], "duration_ms": 60_000}],
        }
    )
    message = _msg("https://music.yandex.ru/users/myname/playlists/1001")

    await handle_link(message, **deps)

    deps["yandex"].get_playlist.assert_awaited_once_with("myname", "1001")


async def test_shared_playlist_link_routes_to_playlist_uuid(deps):
    deps["yandex"].get_playlist_by_uuid = AsyncMock(
        return_value={
            "id": "1036",
            "owner": "yandexmusic",
            "title": "Mix",
            "track_count": 1,
            "duration_ms": 60_000,
            "cover_uri": "x/%%",
            "tracks": [{"title": "s", "artists": ["a"], "duration_ms": 60_000}],
            "playlist_uuid": "3bf96c85-6196-f08d-aac1-000000000000",
        }
    )
    message = _msg("https://music.yandex.ru/playlists/3bf96c85-6196-f08d-aac1-000000000000?utm_source=web&utm_medium=copy_link")

    await handle_link(message, **deps)

    deps["yandex"].get_playlist_by_uuid.assert_awaited_once_with("3bf96c85-6196-f08d-aac1-000000000000")
    message.answer_photo.assert_awaited_once()


async def test_shared_playlist_link_uses_uuid_alias_cache(deps):
    deps["cache"].get = AsyncMock(
        side_effect=[
            None,
            {"owner": "yandexmusic", "kind": "1036"},
            None,
        ]
    )
    deps["yandex"].get_playlist = AsyncMock(
        return_value={
            "id": "1036",
            "owner": "yandexmusic",
            "title": "Mix",
            "track_count": 1,
            "duration_ms": 60_000,
            "cover_uri": "x/%%",
            "tracks": [{"title": "s", "artists": ["a"], "duration_ms": 60_000}],
            "playlist_uuid": "3bf96c85-6196-f08d-aac1-000000000000",
        }
    )
    message = _msg("https://music.yandex.ru/playlists/3bf96c85-6196-f08d-aac1-000000000000")

    await handle_link(message, **deps)

    deps["yandex"].get_playlist.assert_awaited_once_with("yandexmusic", "1036")
    deps["yandex"].get_playlist_by_uuid.assert_not_awaited()
    message.answer_photo.assert_awaited_once()
