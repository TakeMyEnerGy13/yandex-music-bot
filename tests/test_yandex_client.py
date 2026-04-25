import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from bot.services.yandex import YandexMusicClient, YMNotFound, YMTemporaryUnavailable, YMUnauthorized


def _fake_track():
    return SimpleNamespace(
        id="456",
        title="Bohemian Rhapsody",
        artists=[SimpleNamespace(name="Queen")],
        albums=[SimpleNamespace(id="123", title="A Night at the Opera", year=1975, genre="rock")],
        duration_ms=355_000,
        cover_uri="avatars.yandex.net/get-music/x/%%",
    )


@pytest.fixture
def ym_client():
    with patch("bot.services.yandex.YMSyncClient") as cls:
        sync = MagicMock()
        cls.return_value.init.return_value = sync
        client = YandexMusicClient(token="fake")
        client._sync = sync
        yield client


async def test_get_track_returns_dict(ym_client):
    ym_client._sync.tracks.return_value = [_fake_track()]

    got = await ym_client.get_track("456")

    assert got == {
        "id": "456",
        "title": "Bohemian Rhapsody",
        "artists": ["Queen"],
        "album_id": "123",
        "album_title": "A Night at the Opera",
        "album_year": 1975,
        "duration_ms": 355_000,
        "genre": "rock",
        "cover_uri": "avatars.yandex.net/get-music/x/%%",
    }


async def test_get_track_raises_not_found_when_missing(ym_client):
    ym_client._sync.tracks.return_value = []

    with pytest.raises(YMNotFound):
        await ym_client.get_track("999")


async def test_get_track_propagates_unauthorized(ym_client):
    from yandex_music.exceptions import UnauthorizedError

    ym_client._sync.tracks.side_effect = UnauthorizedError("bad token")

    with pytest.raises(YMUnauthorized):
        await ym_client.get_track("1")


async def test_get_playlist_by_uuid_raises_temporary_when_captcha_html(ym_client):
    response = MagicMock()
    response.status_code = 200
    response.url = "https://api.music.yandex.ru/showcaptcha?cc=1"
    response.headers = {"content-type": "text/html"}
    response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

    with patch("bot.services.yandex.httpx.get", return_value=response):
        with pytest.raises(YMTemporaryUnavailable):
            await ym_client.get_playlist_by_uuid("uuid")


async def test_get_playlist_by_uuid_retries_and_succeeds_after_network_error(ym_client):
    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.url = "https://api.music.yandex.ru/playlist/uuid?richTracks=true"
    ok_response.headers = {"content-type": "application/json"}
    ok_response.json.return_value = {
        "result": {
            "owner": {"login": "yandexmusic"},
            "playlistUuid": "uuid",
            "kind": 1036,
            "title": "Mix",
            "trackCount": 1,
            "durationMs": 60_000,
            "cover": {"uri": "x/%%"},
            "tracks": [
                {
                    "track": {
                        "title": "Song",
                        "durationMs": 60_000,
                        "artists": [{"name": "Artist"}],
                    }
                }
            ],
        }
    }

    with patch("bot.services.yandex.httpx.get", side_effect=[httpx.ReadTimeout("slow"), ok_response]) as get_mock:
        with patch("bot.services.yandex.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            playlist = await ym_client.get_playlist_by_uuid("uuid")

    assert get_mock.call_count == 2
    sleep_mock.assert_awaited_once()
    assert playlist["owner"] == "yandexmusic"
    assert playlist["id"] == "1036"


async def test_get_playlist_by_uuid_cooldown_skips_request_after_captcha(ym_client):
    ym_client._playlist_uuid_blocked_until = 200.0

    with patch("bot.services.yandex.time.monotonic", return_value=100.0):
        with patch("bot.services.yandex.httpx.get") as get_mock:
            with pytest.raises(YMTemporaryUnavailable):
                await ym_client.get_playlist_by_uuid("uuid")

    get_mock.assert_not_called()


async def test_get_playlist_by_uuid_sets_cooldown_on_captcha(ym_client):
    response = MagicMock()
    response.status_code = 200
    response.url = "https://api.music.yandex.ru/showcaptcha?cc=1"
    response.headers = {"content-type": "text/html"}
    response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

    with patch("bot.services.yandex.time.monotonic", return_value=100.0):
        with patch("bot.services.yandex.httpx.get", return_value=response):
            with pytest.raises(YMTemporaryUnavailable):
                await ym_client.get_playlist_by_uuid("uuid")

    assert ym_client._playlist_uuid_blocked_until == 280.0


async def test_get_playlist_by_uuid_allows_request_after_cooldown(ym_client):
    ym_client._playlist_uuid_blocked_until = 50.0

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.url = "https://api.music.yandex.ru/playlist/uuid?richTracks=true"
    ok_response.headers = {"content-type": "application/json"}
    ok_response.json.return_value = {
        "result": {
            "owner": {"login": "yandexmusic"},
            "playlistUuid": "uuid",
            "kind": 1036,
            "title": "Mix",
            "trackCount": 1,
            "durationMs": 60_000,
            "cover": {"uri": "x/%%"},
            "tracks": [],
        }
    }

    with patch("bot.services.yandex.time.monotonic", return_value=100.0):
        with patch("bot.services.yandex.httpx.get", return_value=ok_response) as get_mock:
            playlist = await ym_client.get_playlist_by_uuid("uuid")

    assert get_mock.call_count == 1
    assert playlist["owner"] == "yandexmusic"


async def test_get_playlist_by_uuid_deduplicates_parallel_requests(ym_client):
    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.url = "https://api.music.yandex.ru/playlist/uuid?richTracks=true"
    ok_response.headers = {"content-type": "application/json"}
    ok_response.json.return_value = {
        "result": {
            "owner": {"login": "yandexmusic"},
            "playlistUuid": "uuid",
            "kind": 1036,
            "title": "Mix",
            "trackCount": 1,
            "durationMs": 60_000,
            "cover": {"uri": "x/%%"},
            "tracks": [],
        }
    }

    def slow_get(*args, **kwargs):
        time.sleep(0.05)
        return ok_response

    with patch("bot.services.yandex.httpx.get", side_effect=slow_get) as get_mock:
        first, second = await asyncio.gather(
            ym_client.get_playlist_by_uuid("uuid"),
            ym_client.get_playlist_by_uuid("uuid"),
        )

    assert get_mock.call_count == 1
    assert first["owner"] == "yandexmusic"
    assert second["owner"] == "yandexmusic"
