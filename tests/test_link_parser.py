import pytest

from bot.services.link_parser import ParsedLink, parse


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://music.yandex.ru/album/123/track/456",
            ParsedLink(type="track", primary_id="456", secondary_id="123"),
        ),
        (
            "https://music.yandex.ru/track/456",
            ParsedLink(type="track", primary_id="456", secondary_id=None),
        ),
        (
            "https://music.yandex.ru/album/123",
            ParsedLink(type="album", primary_id="123", secondary_id=None),
        ),
        (
            "https://music.yandex.ru/users/myname/playlists/1001",
            ParsedLink(type="playlist", primary_id="1001", secondary_id="myname"),
        ),
        (
            "https://music.yandex.ru/playlists/3bf96c85-6196-f08d-aac1-000000000000",
            ParsedLink(type="playlist", primary_id="3bf96c85-6196-f08d-aac1-000000000000", secondary_id=None),
        ),
        (
            "https://music.yandex.ru/artist/789",
            ParsedLink(type="artist", primary_id="789", secondary_id=None),
        ),
        (
            "https://music.yandex.com/album/1",
            ParsedLink(type="album", primary_id="1", secondary_id=None),
        ),
        (
            "https://music.yandex.by/artist/2",
            ParsedLink(type="artist", primary_id="2", secondary_id=None),
        ),
        (
            "  https://music.yandex.ru/album/123/track/456?utm_source=share  ",
            ParsedLink(type="track", primary_id="456", secondary_id="123"),
        ),
        (
            "https://music.yandex.ru/album/123/",
            ParsedLink(type="album", primary_id="123", secondary_id=None),
        ),
        (
            "https://music.yandex.ru/playlists/3bf96c85-6196-f08d-aac1-000000000000?utm_source=web&utm_medium=copy_link",
            ParsedLink(type="playlist", primary_id="3bf96c85-6196-f08d-aac1-000000000000", secondary_id=None),
        ),
    ],
)
def test_parse_valid(url, expected):
    assert parse(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "https://example.com/album/123",
        "https://music.yandex.ru/",
        "https://music.yandex.ru/album/abc",
        "https://music.yandex.ru/album/123/track/abc",
        "https://spotify.com/track/abc",
        None,
        123,
    ],
)
def test_parse_invalid(url):
    assert parse(url) is None
