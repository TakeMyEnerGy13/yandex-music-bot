from bot.renderers._helpers import cover_url, format_duration
from bot.renderers.track_card import render_track


def test_format_duration():
    assert format_duration(0) == "0:00"
    assert format_duration(59_000) == "0:59"
    assert format_duration(60_000) == "1:00"
    assert format_duration(355_000) == "5:55"
    assert format_duration(3_600_000) == "60:00"


def test_cover_url_replaces_template():
    assert cover_url("avatars.yandex.net/get-music/x/%%") == "https://avatars.yandex.net/get-music/x/400x400"
    assert cover_url("avatars.yandex.net/get/x/%%", size="200x200") == "https://avatars.yandex.net/get/x/200x200"
    assert cover_url(None) is None
    assert cover_url("") is None


def _track_fixture(**overrides):
    base = {
        "id": "456",
        "title": "Bohemian Rhapsody",
        "artists": ["Queen"],
        "album_id": "123",
        "album_title": "A Night at the Opera",
        "album_year": 1975,
        "duration_ms": 355_000,
        "genre": "rock",
    }
    base.update(overrides)
    return base


def test_render_track_full():
    text = render_track(_track_fixture())
    assert "🎵 <b>Bohemian Rhapsody</b>" in text
    assert "👤 Queen" in text
    assert "💿 A Night at the Opera (1975)" in text
    assert "⏱ 5:55" in text
    assert "🎼 rock" in text
    assert "🔗" not in text


def test_render_track_with_songlinks():
    links = {
        "Spotify": "https://open.spotify.com/track/abc",
        "Apple Music": "https://music.apple.com/track/xyz",
    }

    text = render_track(_track_fixture(), songlinks=links)

    assert "🔗 Other platforms:" in text
    assert '<a href="https://open.spotify.com/track/abc">Spotify</a>' in text
    assert '<a href="https://music.apple.com/track/xyz">Apple Music</a>' in text


def test_render_track_escapes_html():
    text = render_track(_track_fixture(title="<script>alert(1)</script>", artists=["AC/DC & Co."]))
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "AC/DC &amp; Co." in text


def test_render_track_handles_missing_optional_fields():
    text = render_track(_track_fixture(album_year=None, genre=None))
    assert "(—)" in text
    assert "🎼" not in text
