from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from bot.services.songlink import SongLinkClient

SAMPLE_RESPONSE = {
    "linksByPlatform": {
        "spotify": {"url": "https://open.spotify.com/track/abc"},
        "appleMusic": {"url": "https://music.apple.com/track/xyz"},
        "youtubeMusic": {"url": "https://music.youtube.com/watch?v=qqq"},
        "deezer": {"url": "https://deezer.com/track/123"},
        "tidal": {"url": "https://listen.tidal.com/track/456"},
        "amazonMusic": {"url": "https://music.amazon.com/albums/album?trackAsin=xyz"},
    }
}


@pytest.fixture
async def client():
    songlink = SongLinkClient(timeout=2.0)
    yield songlink
    await songlink.close()


@respx.mock
async def test_returns_known_platforms(client):
    respx.get("https://api.song.link/v1-alpha.1/links").mock(
        return_value=httpx.Response(200, json=SAMPLE_RESPONSE)
    )

    got = await client.get_links("https://music.yandex.ru/album/1/track/1")

    assert got == {
        "Spotify": "https://open.spotify.com/track/abc",
        "Apple Music": "https://music.apple.com/track/xyz",
        "YouTube Music": "https://music.youtube.com/watch?v=qqq",
        "Deezer": "https://deezer.com/track/123",
        "TIDAL": "https://listen.tidal.com/track/456",
        "Amazon Music": "https://music.amazon.com/albums/album?trackAsin=xyz",
    }


@respx.mock
async def test_returns_empty_on_timeout(client):
    respx.get("https://api.song.link/v1-alpha.1/links").mock(side_effect=httpx.ReadTimeout("slow"))
    assert await client.get_links("https://music.yandex.ru/track/1") == {}


@respx.mock
async def test_returns_empty_on_5xx(client):
    respx.get("https://api.song.link/v1-alpha.1/links").mock(return_value=httpx.Response(503))
    assert await client.get_links("https://music.yandex.ru/track/1") == {}


@respx.mock
async def test_returns_empty_on_unexpected_payload(client):
    respx.get("https://api.song.link/v1-alpha.1/links").mock(return_value=httpx.Response(200, json={"weird": True}))
    assert await client.get_links("https://music.yandex.ru/track/1") == {}


async def test_retries_once_after_timeout_then_succeeds(client):
    ok_response = httpx.Response(
        200,
        json={
            "linksByPlatform": {
                "spotify": {"url": "https://open.spotify.com/track/abc"},
            }
        },
    )

    with patch.object(
        client._client,
        "get",
        new=AsyncMock(side_effect=[httpx.ReadTimeout("slow"), ok_response]),
    ) as get_mock:
        with patch("bot.services.songlink.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            links = await client.get_links("https://music.yandex.ru/track/1")

    assert links == {"Spotify": "https://open.spotify.com/track/abc"}
    assert get_mock.await_count == 2
    sleep_mock.assert_awaited_once()
