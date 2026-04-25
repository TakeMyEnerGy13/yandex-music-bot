from bot.renderers.album_card import render_album
from bot.renderers.artist_card import render_artist
from bot.renderers.playlist_card import render_playlist
from bot.renderers.similar_list import render_similar


def _album_fixture(**overrides):
    base = {
        "id": "123",
        "title": "A Night at the Opera",
        "artists": ["Queen"],
        "year": 1975,
        "track_count": 12,
        "duration_ms": 2_588_000,
        "tracks": [{"title": f"Track {index}", "duration_ms": 200_000} for index in range(1, 13)],
    }
    base.update(overrides)
    return base


def test_render_album_includes_meta_and_tracks():
    text = render_album(_album_fixture())
    assert "💿 <b>A Night at the Opera</b>" in text
    assert "👤 Queen · 1975 · 12 tracks · 43:08" in text
    assert "1. Track 1 — 3:20" in text
    assert "12. Track 12 — 3:20" in text


def test_render_album_truncates_to_15_tracks():
    big = _album_fixture(
        track_count=30,
        tracks=[{"title": f"T{index}", "duration_ms": 100_000} for index in range(1, 31)],
    )
    text = render_album(big)
    assert "1. T1" in text
    assert "15. T15" in text
    assert "16. T16" not in text
    assert "… and 15 more" in text


def test_render_artist_includes_top_tracks():
    artist = {
        "id": "789",
        "name": "Queen",
        "top_tracks": [
            {"title": "Bohemian Rhapsody", "duration_ms": 355_000},
            {"title": "Don't Stop Me Now", "duration_ms": 209_000},
        ],
    }
    text = render_artist(artist)
    assert "👤 <b>Queen</b>" in text
    assert "1. Bohemian Rhapsody — 5:55" in text
    assert "2. Don't Stop Me Now — 3:29" in text


def test_render_playlist_includes_first_10():
    playlist = {
        "id": "1001",
        "owner": "myname",
        "title": "My Mix",
        "track_count": 50,
        "duration_ms": 10_000_000,
        "tracks": [
            {"title": f"Song {index}", "artists": ["Artist"], "duration_ms": 200_000}
            for index in range(1, 51)
        ],
    }
    text = render_playlist(playlist)
    assert "📃 <b>My Mix</b>" in text
    assert "by myname · 50 tracks" in text
    assert "1. Song 1 — Artist · 3:20" in text
    assert "10. Song 10 — Artist · 3:20" in text
    assert "11. Song 11" not in text
    assert "… and 40 more" in text


def test_render_similar_with_yandex_links():
    similar = [
        {"id": "1", "title": "Stairway to Heaven", "artists": ["Led Zeppelin"], "duration_ms": 482_000},
        {"id": "2", "title": "Hotel California", "artists": ["Eagles"], "duration_ms": 390_000},
    ]
    text = render_similar(source_title="Bohemian Rhapsody", tracks=similar)
    assert "🎯 Похожие на «Bohemian Rhapsody»:" in text
    assert '1. <a href="https://music.yandex.ru/track/1">Stairway to Heaven</a> — Led Zeppelin · 8:02' in text
    assert '2. <a href="https://music.yandex.ru/track/2">Hotel California</a> — Eagles · 6:30' in text
