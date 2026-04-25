# Yandex.Music Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot (Python 3.12 + aiogram 3 + Redis) that returns rich info for Yandex.Music links — tracks, albums, playlists, artists — with cross-platform links via song.link, similar-track discovery, and inline-mode support. Deployed via Docker Compose to user's Ubuntu 22.04 VPS.

**Architecture:** Three layers — handlers (thin aiogram routers), services (LinkParser / YandexMusicClient / SongLinkClient / Cache), renderers (pure functions producing HTML caption + InlineKeyboard). Handlers call services, services hit Redis cache before external APIs. All external APIs are mocked in tests.

**Tech Stack:** Python 3.12, aiogram 3.x, yandex-music (PyPI), httpx (async), redis-py asyncio, pydantic-settings, pytest + pytest-asyncio + respx + fakeredis. uv for dependency management. Docker + docker-compose for deploy.

**Source spec:** `docs/superpowers/specs/2026-04-25-yandex-music-bot-design.md`

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `bot/__init__.py`, `bot/handlers/__init__.py`, `bot/services/__init__.py`, `bot/renderers/__init__.py`
- Create: `tests/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "yandex-music-bot"
version = "0.1.0"
description = "Telegram bot for Yandex.Music links"
requires-python = ">=3.12"
dependencies = [
    "aiogram>=3.13,<4",
    "yandex-music>=2.2.0",
    "httpx>=0.27",
    "redis>=5.0",
    "pydantic-settings>=2.5",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
    "fakeredis>=2.24",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Write `.env.example`**

```
TELEGRAM_BOT_TOKEN=put-your-bot-token-from-botfather-here
YANDEX_MUSIC_TOKEN=put-your-yandex-music-token-here
REDIS_URL=redis://redis:6379/0
LOG_LEVEL=INFO
RATE_LIMIT_PER_MINUTE=10
SONGLINK_TIMEOUT=2.0
INLINE_TIMEOUT=0.8
```

- [ ] **Step 3: Create empty package files**

```bash
touch bot/__init__.py bot/handlers/__init__.py bot/services/__init__.py bot/renderers/__init__.py
touch tests/__init__.py
```

- [ ] **Step 4: Write `tests/conftest.py`**

```python
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 5: Install deps and verify**

```bash
uv sync
uv run pytest --collect-only
```

Expected: pytest reports "no tests collected" (we have no tests yet) — confirms environment works.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example bot/ tests/
git commit -m "feat: project scaffolding (pyproject, package structure, env template)"
```

---

## Task 2: Config module

**Files:**
- Create: `bot/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from pydantic import ValidationError
from bot.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-test")
    monkeypatch.setenv("YANDEX_MUSIC_TOKEN", "ym-test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")

    s = Settings()

    assert s.telegram_bot_token == "tg-test"
    assert s.yandex_music_token == "ym-test"
    assert s.redis_url == "redis://localhost:6379/1"
    assert s.log_level == "INFO"  # default
    assert s.rate_limit_per_minute == 10  # default
    assert s.songlink_timeout == 2.0
    assert s.inline_timeout == 0.8


def test_settings_requires_tokens(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("YANDEX_MUSIC_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
```

- [ ] **Step 2: Run test — verify it fails**

```bash
uv run pytest tests/test_config.py -v
```

Expected: ImportError or ModuleNotFoundError (no `bot.config` yet).

- [ ] **Step 3: Implement `bot/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str
    yandex_music_token: str
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"
    rate_limit_per_minute: int = 10
    songlink_timeout: float = 2.0
    inline_timeout: float = 0.8
```

- [ ] **Step 4: Run tests — verify pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/config.py tests/test_config.py
git commit -m "feat(config): pydantic-settings module with env validation"
```

---

## Task 3: LinkParser

**Files:**
- Create: `bot/services/link_parser.py`
- Test: `tests/test_link_parser.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_link_parser.py
import pytest
from bot.services.link_parser import parse, ParsedLink


@pytest.mark.parametrize("url,expected", [
    # full track URL
    (
        "https://music.yandex.ru/album/123/track/456",
        ParsedLink(type="track", primary_id="456", secondary_id="123"),
    ),
    # short track URL
    (
        "https://music.yandex.ru/track/456",
        ParsedLink(type="track", primary_id="456", secondary_id=None),
    ),
    # album
    (
        "https://music.yandex.ru/album/123",
        ParsedLink(type="album", primary_id="123", secondary_id=None),
    ),
    # playlist
    (
        "https://music.yandex.ru/users/myname/playlists/1001",
        ParsedLink(type="playlist", primary_id="1001", secondary_id="myname"),
    ),
    # artist
    (
        "https://music.yandex.ru/artist/789",
        ParsedLink(type="artist", primary_id="789", secondary_id=None),
    ),
    # alternate domains
    ("https://music.yandex.com/album/1", ParsedLink(type="album", primary_id="1")),
    ("https://music.yandex.by/artist/2", ParsedLink(type="artist", primary_id="2")),
    # whitespace + tracking params
    (
        "  https://music.yandex.ru/album/123/track/456?utm_source=share  ",
        ParsedLink(type="track", primary_id="456", secondary_id="123"),
    ),
    # trailing slash
    ("https://music.yandex.ru/album/123/", ParsedLink(type="album", primary_id="123")),
])
def test_parse_valid(url, expected):
    assert parse(url) == expected


@pytest.mark.parametrize("url", [
    "",
    "not a url",
    "https://example.com/album/123",
    "https://music.yandex.ru/",
    "https://music.yandex.ru/album/abc",  # non-numeric id
    "https://music.yandex.ru/album/123/track/abc",
    "https://spotify.com/track/abc",
    None,
    123,
])
def test_parse_invalid(url):
    assert parse(url) is None
```

- [ ] **Step 2: Run test — verify it fails**

```bash
uv run pytest tests/test_link_parser.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `bot/services/link_parser.py`**

```python
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

LinkType = Literal["track", "album", "playlist", "artist"]

ALLOWED_HOSTS = {
    "music.yandex.ru",
    "music.yandex.com",
    "music.yandex.by",
    "music.yandex.kz",
}

_PATTERNS: list[tuple[re.Pattern[str], LinkType, bool]] = [
    # (regex, type, has_secondary_id)
    (re.compile(r"^/album/(\d+)/track/(\d+)$"), "track", True),
    (re.compile(r"^/track/(\d+)$"), "track", False),
    (re.compile(r"^/album/(\d+)$"), "album", False),
    (re.compile(r"^/users/([^/]+)/playlists/(\d+)$"), "playlist", True),
    (re.compile(r"^/artist/(\d+)$"), "artist", False),
]


@dataclass(frozen=True)
class ParsedLink:
    type: LinkType
    primary_id: str
    secondary_id: str | None = None


def parse(url) -> ParsedLink | None:
    if not isinstance(url, str):
        return None

    parsed = urlparse(url.strip())
    if parsed.netloc not in ALLOWED_HOSTS:
        return None

    path = parsed.path.rstrip("/")

    for pattern, link_type, has_secondary in _PATTERNS:
        m = pattern.fullmatch(path)
        if not m:
            continue
        if link_type == "track" and has_secondary:
            return ParsedLink(type="track", primary_id=m.group(2), secondary_id=m.group(1))
        if link_type == "playlist":
            return ParsedLink(type="playlist", primary_id=m.group(2), secondary_id=m.group(1))
        return ParsedLink(type=link_type, primary_id=m.group(1))

    return None
```

- [ ] **Step 4: Run tests — verify pass**

```bash
uv run pytest tests/test_link_parser.py -v
```

Expected: all parametrized cases pass.

- [ ] **Step 5: Commit**

```bash
git add bot/services/link_parser.py tests/test_link_parser.py
git commit -m "feat(parser): URL → ParsedLink for track/album/playlist/artist"
```

---

## Task 4: Renderer helpers + track card

**Files:**
- Create: `bot/renderers/_helpers.py`
- Create: `bot/renderers/track_card.py`
- Test: `tests/test_track_renderer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_track_renderer.py
from bot.renderers.track_card import render_track
from bot.renderers._helpers import format_duration, cover_url


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
    assert "🔗" not in text  # no songlinks passed


def test_render_track_with_songlinks():
    links = {"Spotify": "https://open.spotify.com/track/abc", "Apple Music": "https://music.apple.com/track/xyz"}
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
    assert "🎼" not in text  # no genre block
```

- [ ] **Step 2: Run test — verify it fails**

```bash
uv run pytest tests/test_track_renderer.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `bot/renderers/_helpers.py`**

```python
from html import escape as _escape


def format_duration(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


def cover_url(uri_template: str | None, size: str = "400x400") -> str | None:
    if not uri_template:
        return None
    return f"https://{uri_template.replace('%%', size)}"


def html_escape(text: str) -> str:
    return _escape(str(text), quote=True)
```

- [ ] **Step 4: Implement `bot/renderers/track_card.py`**

```python
from bot.renderers._helpers import format_duration, html_escape


def render_track(track: dict, songlinks: dict[str, str] | None = None) -> str:
    title = html_escape(track["title"])
    artists = html_escape(", ".join(track["artists"]))
    album = html_escape(track["album_title"])
    year = track.get("album_year") or "—"
    duration = format_duration(track["duration_ms"])
    genre = track.get("genre")

    duration_line = f"⏱ {duration}"
    if genre:
        duration_line += f" · 🎼 {html_escape(genre)}"

    lines = [
        f"🎵 <b>{title}</b>",
        f"👤 {artists}",
        f"💿 {album} ({year})",
        duration_line,
    ]

    if songlinks:
        platform_links = " · ".join(
            f'<a href="{html_escape(url)}">{html_escape(name)}</a>'
            for name, url in songlinks.items()
        )
        lines += ["", f"🔗 Other platforms: {platform_links}"]

    return "\n".join(lines)
```

- [ ] **Step 5: Run tests — verify pass**

```bash
uv run pytest tests/test_track_renderer.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add bot/renderers/ tests/test_track_renderer.py
git commit -m "feat(renderers): track card + duration/cover/escape helpers"
```

---

## Task 5: Album / Artist / Playlist / Similar-list renderers

**Files:**
- Create: `bot/renderers/album_card.py`
- Create: `bot/renderers/artist_card.py`
- Create: `bot/renderers/playlist_card.py`
- Create: `bot/renderers/similar_list.py`
- Test: `tests/test_other_renderers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_other_renderers.py
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
        "tracks": [
            {"title": f"Track {i}", "duration_ms": 200_000} for i in range(1, 13)
        ],
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
        tracks=[{"title": f"T{i}", "duration_ms": 100_000} for i in range(1, 31)],
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
            {"title": f"Song {i}", "artists": ["Artist"], "duration_ms": 200_000}
            for i in range(1, 51)
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_other_renderers.py -v
```

Expected: ImportError on each renderer.

- [ ] **Step 3: Implement `bot/renderers/album_card.py`**

```python
from bot.renderers._helpers import format_duration, html_escape

MAX_TRACKS = 15


def render_album(album: dict) -> str:
    title = html_escape(album["title"])
    artists = html_escape(", ".join(album["artists"]))
    year = album.get("year") or "—"
    track_count = album["track_count"]
    duration = format_duration(album["duration_ms"])

    header = [
        f"💿 <b>{title}</b>",
        f"👤 {artists} · {year} · {track_count} tracks · {duration}",
        "",
    ]

    tracks = album["tracks"][:MAX_TRACKS]
    body = [
        f"{i}. {html_escape(t['title'])} — {format_duration(t['duration_ms'])}"
        for i, t in enumerate(tracks, start=1)
    ]

    if track_count > MAX_TRACKS:
        body.append(f"… and {track_count - MAX_TRACKS} more")

    return "\n".join(header + body)
```

- [ ] **Step 4: Implement `bot/renderers/artist_card.py`**

```python
from bot.renderers._helpers import format_duration, html_escape


def render_artist(artist: dict) -> str:
    name = html_escape(artist["name"])
    lines = [f"👤 <b>{name}</b>", "", "Top tracks:"]
    for i, t in enumerate(artist.get("top_tracks", [])[:5], start=1):
        lines.append(
            f"{i}. {html_escape(t['title'])} — {format_duration(t['duration_ms'])}"
        )
    return "\n".join(lines)
```

- [ ] **Step 5: Implement `bot/renderers/playlist_card.py`**

```python
from bot.renderers._helpers import format_duration, html_escape

MAX_TRACKS = 10


def render_playlist(playlist: dict) -> str:
    title = html_escape(playlist["title"])
    owner = html_escape(playlist["owner"])
    track_count = playlist["track_count"]
    duration = format_duration(playlist["duration_ms"])

    header = [
        f"📃 <b>{title}</b>",
        f"by {owner} · {track_count} tracks · {duration}",
        "",
    ]

    tracks = playlist["tracks"][:MAX_TRACKS]
    body = [
        f"{i}. {html_escape(t['title'])} — {html_escape(', '.join(t['artists']))} · {format_duration(t['duration_ms'])}"
        for i, t in enumerate(tracks, start=1)
    ]

    if track_count > MAX_TRACKS:
        body.append(f"… and {track_count - MAX_TRACKS} more")

    return "\n".join(header + body)
```

- [ ] **Step 6: Implement `bot/renderers/similar_list.py`**

```python
from bot.renderers._helpers import format_duration, html_escape


def render_similar(source_title: str, tracks: list[dict]) -> str:
    lines = [f"🎯 Похожие на «{html_escape(source_title)}»:", ""]
    for i, t in enumerate(tracks, start=1):
        link = f"https://music.yandex.ru/track/{t['id']}"
        artists = html_escape(", ".join(t["artists"]))
        lines.append(
            f'{i}. <a href="{link}">{html_escape(t["title"])}</a> — {artists} · {format_duration(t["duration_ms"])}'
        )
    return "\n".join(lines)
```

- [ ] **Step 7: Run all renderer tests — verify pass**

```bash
uv run pytest tests/test_other_renderers.py tests/test_track_renderer.py -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add bot/renderers/album_card.py bot/renderers/artist_card.py bot/renderers/playlist_card.py bot/renderers/similar_list.py tests/test_other_renderers.py
git commit -m "feat(renderers): album, artist, playlist, similar-list cards"
```

---

## Task 6: Cache module

**Files:**
- Create: `bot/services/cache.py`
- Test: `tests/test_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cache.py
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from redis.exceptions import RedisError

from bot.services.cache import Cache


@pytest.fixture
async def cache():
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    c = Cache.__new__(Cache)
    c._redis = fake
    yield c
    await fake.aclose()


async def test_set_then_get_returns_value(cache):
    await cache.set("k", {"a": 1, "b": [2, 3]}, ttl_seconds=60)
    assert await cache.get("k") == {"a": 1, "b": [2, 3]}


async def test_get_missing_returns_none(cache):
    assert await cache.get("missing") is None


async def test_ttl_is_applied(cache):
    await cache.set("k", "v", ttl_seconds=60)
    ttl = await cache._redis.ttl("k")
    assert 0 < ttl <= 60


async def test_get_returns_none_on_redis_error():
    c = Cache.__new__(Cache)
    c._redis = AsyncMock()
    c._redis.get.side_effect = RedisError("down")
    assert await c.get("k") is None


async def test_set_swallows_redis_error():
    c = Cache.__new__(Cache)
    c._redis = AsyncMock()
    c._redis.set.side_effect = RedisError("down")
    # must not raise
    await c.set("k", "v", ttl_seconds=10)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_cache.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `bot/services/cache.py`**

```python
import json
import logging
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)


class Cache:
    def __init__(self, redis_url: str):
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self._redis.get(key)
        except RedisError as e:
            log.warning("cache.get failed key=%s err=%s", key, e)
            return None
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        try:
            await self._redis.set(key, json.dumps(value), ex=ttl_seconds)
        except RedisError as e:
            log.warning("cache.set failed key=%s err=%s", key, e)

    async def close(self) -> None:
        try:
            await self._redis.aclose()
        except RedisError:
            pass
```

- [ ] **Step 4: Run tests — verify pass**

```bash
uv run pytest tests/test_cache.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/services/cache.py tests/test_cache.py
git commit -m "feat(cache): Redis JSON cache with graceful degradation on errors"
```

---

## Task 7: YandexMusicClient

**Files:**
- Create: `bot/services/yandex.py`
- Test: `tests/test_yandex_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_yandex_client.py
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bot.services.yandex import YandexMusicClient, YMNotFound, YMUnauthorized


def _fake_track():
    return SimpleNamespace(
        id="456",
        title="Bohemian Rhapsody",
        artists=[SimpleNamespace(name="Queen")],
        albums=[SimpleNamespace(title="A Night at the Opera", year=1975, genre="rock")],
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_yandex_client.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `bot/services/yandex.py`**

```python
import asyncio
import logging
from typing import Any

from yandex_music import Client as YMSyncClient
from yandex_music.exceptions import NotFoundError, UnauthorizedError

log = logging.getLogger(__name__)


class YMError(Exception):
    pass


class YMNotFound(YMError):
    pass


class YMUnauthorized(YMError):
    pass


def _to_track_dict(track) -> dict[str, Any]:
    album = track.albums[0] if track.albums else None
    return {
        "id": str(track.id),
        "title": track.title,
        "artists": [a.name for a in track.artists],
        "album_title": album.title if album else "",
        "album_year": album.year if album else None,
        "duration_ms": track.duration_ms,
        "genre": album.genre if album else None,
        "cover_uri": track.cover_uri,
    }


def _to_album_dict(album) -> dict[str, Any]:
    tracks = []
    if album.volumes:
        for vol in album.volumes:
            for t in vol:
                tracks.append({"title": t.title, "duration_ms": t.duration_ms})
    return {
        "id": str(album.id),
        "title": album.title,
        "artists": [a.name for a in album.artists],
        "year": album.year,
        "track_count": album.track_count or len(tracks),
        "duration_ms": sum(t["duration_ms"] for t in tracks),
        "cover_uri": album.cover_uri,
        "tracks": tracks,
    }


def _to_artist_dict(artist, top_tracks) -> dict[str, Any]:
    return {
        "id": str(artist.id),
        "name": artist.name,
        "cover_uri": artist.cover.items_uri[0] if artist.cover and artist.cover.items_uri else None,
        "top_tracks": [
            {"id": str(t.id), "title": t.title, "duration_ms": t.duration_ms}
            for t in top_tracks[:5]
        ],
    }


def _to_playlist_dict(playlist) -> dict[str, Any]:
    tracks = []
    for short in (playlist.tracks or []):
        t = short.track
        if not t:
            continue
        tracks.append({
            "title": t.title,
            "artists": [a.name for a in t.artists],
            "duration_ms": t.duration_ms,
        })
    return {
        "id": str(playlist.kind),
        "owner": playlist.owner.login if playlist.owner else "",
        "title": playlist.title,
        "track_count": playlist.track_count or len(tracks),
        "duration_ms": sum(t["duration_ms"] for t in tracks),
        "cover_uri": playlist.cover.uri if playlist.cover else None,
        "tracks": tracks,
    }


class YandexMusicClient:
    def __init__(self, token: str):
        self._sync = YMSyncClient(token).init()

    async def _run(self, fn, *args, **kwargs):
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except UnauthorizedError as e:
            raise YMUnauthorized(str(e)) from e
        except NotFoundError as e:
            raise YMNotFound(str(e)) from e

    async def get_track(self, track_id: str) -> dict:
        tracks = await self._run(self._sync.tracks, [track_id])
        if not tracks:
            raise YMNotFound(f"track {track_id} not found")
        return _to_track_dict(tracks[0])

    async def get_album(self, album_id: str) -> dict:
        album = await self._run(self._sync.albums_with_tracks, album_id)
        if not album:
            raise YMNotFound(f"album {album_id} not found")
        return _to_album_dict(album)

    async def get_artist(self, artist_id: str) -> dict:
        brief = await self._run(self._sync.artists_brief_info, artist_id)
        if not brief or not brief.artist:
            raise YMNotFound(f"artist {artist_id} not found")
        return _to_artist_dict(brief.artist, brief.popular_tracks or [])

    async def get_playlist(self, owner: str, kind: str) -> dict:
        playlist = await self._run(self._sync.users_playlists, kind, owner)
        if not playlist:
            raise YMNotFound(f"playlist {owner}/{kind} not found")
        return _to_playlist_dict(playlist)

    async def get_similar(self, track_id: str) -> list[dict]:
        sim = await self._run(self._sync.tracks_similar, track_id)
        if not sim or not sim.similar_tracks:
            return []
        return [
            {
                "id": str(t.id),
                "title": t.title,
                "artists": [a.name for a in t.artists],
                "duration_ms": t.duration_ms,
            }
            for t in sim.similar_tracks[:5]
        ]
```

- [ ] **Step 4: Run tests — verify pass**

```bash
uv run pytest tests/test_yandex_client.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/services/yandex.py tests/test_yandex_client.py
git commit -m "feat(yandex): async wrapper over yandex-music with typed errors"
```

---

## Task 8: SongLinkClient

**Files:**
- Create: `bot/services/songlink.py`
- Test: `tests/test_songlink.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_songlink.py
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
    }
}


@pytest.fixture
async def client():
    c = SongLinkClient(timeout=2.0)
    yield c
    await c.close()


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
    }


@respx.mock
async def test_returns_empty_on_timeout(client):
    respx.get("https://api.song.link/v1-alpha.1/links").mock(
        side_effect=httpx.ReadTimeout("slow")
    )
    assert await client.get_links("https://music.yandex.ru/track/1") == {}


@respx.mock
async def test_returns_empty_on_5xx(client):
    respx.get("https://api.song.link/v1-alpha.1/links").mock(
        return_value=httpx.Response(503)
    )
    assert await client.get_links("https://music.yandex.ru/track/1") == {}


@respx.mock
async def test_returns_empty_on_unexpected_payload(client):
    respx.get("https://api.song.link/v1-alpha.1/links").mock(
        return_value=httpx.Response(200, json={"weird": True})
    )
    assert await client.get_links("https://music.yandex.ru/track/1") == {}
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_songlink.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `bot/services/songlink.py`**

```python
import logging
import httpx

log = logging.getLogger(__name__)

PLATFORMS = {
    "spotify": "Spotify",
    "appleMusic": "Apple Music",
    "youtubeMusic": "YouTube Music",
}

API_URL = "https://api.song.link/v1-alpha.1/links"


class SongLinkClient:
    def __init__(self, timeout: float = 2.0):
        self._client = httpx.AsyncClient(timeout=timeout)

    async def get_links(self, yandex_url: str) -> dict[str, str]:
        try:
            resp = await self._client.get(API_URL, params={"url": yandex_url, "userCountry": "RU"})
        except httpx.HTTPError as e:
            log.warning("songlink request failed: %s", e)
            return {}
        if resp.status_code != 200:
            log.warning("songlink non-200: %s", resp.status_code)
            return {}
        try:
            data = resp.json()
            links = data["linksByPlatform"]
        except (KeyError, ValueError):
            return {}
        return {
            label: links[key]["url"]
            for key, label in PLATFORMS.items()
            if key in links and "url" in links[key]
        }

    async def close(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 4: Run tests — verify pass**

```bash
uv run pytest tests/test_songlink.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/services/songlink.py tests/test_songlink.py
git commit -m "feat(songlink): cross-platform links via song.link with graceful degradation"
```

---

## Task 9: Keyboards module

**Files:**
- Create: `bot/keyboards.py`
- Test: `tests/test_keyboards.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_keyboards.py
from bot.keyboards import track_keyboard, similar_drilldown_keyboard


def test_track_keyboard_has_similar_and_open_buttons():
    kb = track_keyboard(track_id="456")
    rows = kb.inline_keyboard
    assert len(rows) >= 1
    flat = [b for row in rows for b in row]
    callback_buttons = [b for b in flat if b.callback_data]
    url_buttons = [b for b in flat if b.url]
    assert any(b.callback_data == "similar:456" for b in callback_buttons)
    assert any("music.yandex.ru/track/456" in b.url for b in url_buttons)


def test_similar_drilldown_has_five_numeric_buttons():
    kb = similar_drilldown_keyboard(["1", "2", "3", "4", "5"])
    flat = [b for row in kb.inline_keyboard for b in row]
    assert len(flat) == 5
    assert {b.text for b in flat} == {"1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"}
    assert [b.callback_data for b in flat] == [
        "track_card:1", "track_card:2", "track_card:3", "track_card:4", "track_card:5"
    ]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_keyboards.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `bot/keyboards.py`**

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

NUMBER_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


def track_keyboard(track_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎯 Похожие треки", callback_data=f"similar:{track_id}")
    b.button(text="▶️ Открыть в Яндекс.Музыке", url=f"https://music.yandex.ru/track/{track_id}")
    b.adjust(1)
    return b.as_markup()


def similar_drilldown_keyboard(track_ids: list[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, tid in enumerate(track_ids[:5]):
        b.button(text=NUMBER_EMOJI[i], callback_data=f"track_card:{tid}")
    b.adjust(5)
    return b.as_markup()


def album_open_keyboard(album_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="▶️ Открыть в Яндекс.Музыке", url=f"https://music.yandex.ru/album/{album_id}")
    return b.as_markup()


def artist_open_keyboard(artist_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="▶️ Открыть в Яндекс.Музыке", url=f"https://music.yandex.ru/artist/{artist_id}")
    return b.as_markup()


def playlist_open_keyboard(owner: str, kind: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="▶️ Открыть в Яндекс.Музыке",
             url=f"https://music.yandex.ru/users/{owner}/playlists/{kind}")
    return b.as_markup()
```

- [ ] **Step 4: Run tests — verify pass**

```bash
uv run pytest tests/test_keyboards.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/keyboards.py tests/test_keyboards.py
git commit -m "feat(keyboards): inline button factories for cards"
```

---

## Task 10: Bot entrypoint + system handlers (`/start`, `/help`, `/ping`)

**Files:**
- Create: `bot/main.py`
- Create: `bot/handlers/system.py`
- Test: `tests/test_system_handlers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_system_handlers.py
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import Message

from bot.handlers.system import cmd_start, cmd_help, cmd_ping


def _msg():
    m = MagicMock(spec=Message)
    m.answer = AsyncMock()
    return m


async def test_start_introduces_bot_and_mentions_inline():
    m = _msg()
    await cmd_start(m)
    text = m.answer.call_args.args[0]
    assert "Yandex.Music" in text or "Яндекс.Музык" in text
    assert "@" in text  # inline tip


async def test_help_lists_supported_link_types():
    m = _msg()
    await cmd_help(m)
    text = m.answer.call_args.args[0]
    for kind in ("track", "album", "playlist", "artist"):
        assert kind in text


async def test_ping_replies_pong():
    m = _msg()
    await cmd_ping(m)
    m.answer.assert_awaited_once_with("pong")
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_system_handlers.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `bot/handlers/system.py`**

```python
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

router = Router(name="system")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    me = await message.bot.get_me() if message.bot else None
    handle = f"@{me.username}" if me and me.username else "@your_bot"
    await message.answer(
        "👋 Привет! Я бот для Yandex.Music.\n\n"
        "Кинь мне ссылку на трек / альбом / плейлист / артиста — "
        "верну красивую карточку с инфой и ссылками на Spotify / Apple Music / YouTube Music.\n\n"
        f"💡 <b>Совет:</b> вызывай меня в любом чате через "
        f"<code>{handle} ссылка</code> чтобы шерить треки моментально (inline-режим).",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Поддерживаемые ссылки:\n"
        "• track — https://music.yandex.ru/album/X/track/Y\n"
        "• album — https://music.yandex.ru/album/X\n"
        "• playlist — https://music.yandex.ru/users/U/playlists/P\n"
        "• artist — https://music.yandex.ru/artist/X\n\n"
        "Команды:\n"
        "/start — приветствие\n"
        "/help — эта справка\n"
        "/ping — проверить, что бот жив",
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    await message.answer("pong")
```

- [ ] **Step 4: Implement `bot/main.py`**

```python
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import Settings
from bot.handlers import system
from bot.services.cache import Cache
from bot.services.songlink import SongLinkClient
from bot.services.yandex import YandexMusicClient

log = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def main() -> None:
    settings = Settings()
    _setup_logging(settings.log_level)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    cache = Cache(settings.redis_url)
    yandex = YandexMusicClient(settings.yandex_music_token)
    songlink = SongLinkClient(timeout=settings.songlink_timeout)

    dp["cache"] = cache
    dp["yandex"] = yandex
    dp["songlink"] = songlink
    dp["settings"] = settings

    dp.include_router(system.router)

    log.info("bot starting (polling mode)")
    try:
        await dp.start_polling(bot)
    finally:
        await songlink.close()
        await cache.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Run tests — verify pass**

```bash
uv run pytest tests/test_system_handlers.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add bot/main.py bot/handlers/system.py tests/test_system_handlers.py
git commit -m "feat(handlers): /start, /help, /ping + bot entrypoint with DI"
```

---

## Task 11: Link message handler (track / album / artist / playlist routing)

**Files:**
- Create: `bot/handlers/link.py`
- Modify: `bot/main.py` — register `link.router`
- Test: `tests/test_link_handler.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_link_handler.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from bot.handlers.link import handle_link


def _msg(text: str) -> MagicMock:
    m = MagicMock(spec=Message)
    m.text = text
    m.answer = AsyncMock()
    m.answer_photo = AsyncMock()
    return m


@pytest.fixture
def deps():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    yandex = MagicMock()
    yandex.get_track = AsyncMock(return_value={
        "id": "456", "title": "Bohemian Rhapsody", "artists": ["Queen"],
        "album_title": "A Night at the Opera", "album_year": 1975,
        "duration_ms": 355_000, "genre": "rock",
        "cover_uri": "avatars.yandex.net/x/%%",
    })
    yandex.get_album = AsyncMock()
    yandex.get_artist = AsyncMock()
    yandex.get_playlist = AsyncMock()
    songlink = MagicMock()
    songlink.get_links = AsyncMock(return_value={"Spotify": "https://open.spotify.com/track/x"})
    return {"cache": cache, "yandex": yandex, "songlink": songlink}


async def test_track_link_sends_photo_with_caption(deps):
    m = _msg("https://music.yandex.ru/album/123/track/456")
    await handle_link(m, **deps)

    deps["yandex"].get_track.assert_awaited_once_with("456")
    deps["songlink"].get_links.assert_awaited_once()
    m.answer_photo.assert_awaited_once()
    kwargs = m.answer_photo.call_args.kwargs
    assert "Bohemian Rhapsody" in kwargs["caption"]
    assert "Spotify" in kwargs["caption"]
    assert kwargs["reply_markup"] is not None


async def test_track_link_uses_cache_on_hit(deps):
    deps["cache"].get = AsyncMock(return_value={
        "track": {
            "id": "456", "title": "Cached", "artists": ["X"],
            "album_title": "A", "album_year": 2020,
            "duration_ms": 100_000, "genre": None,
            "cover_uri": "x/%%",
        },
        "songlinks": {"Spotify": "https://x"},
    })
    m = _msg("https://music.yandex.ru/track/456")
    await handle_link(m, **deps)

    deps["yandex"].get_track.assert_not_awaited()
    deps["songlink"].get_links.assert_not_awaited()
    m.answer_photo.assert_awaited_once()


async def test_unknown_link_replies_friendly_error(deps):
    m = _msg("https://example.com/whatever")
    await handle_link(m, **deps)
    m.answer.assert_awaited_once()
    assert "не похоже" in m.answer.call_args.args[0].lower() or "поддерж" in m.answer.call_args.args[0].lower()
    m.answer_photo.assert_not_awaited()


async def test_album_link_routes_to_album(deps):
    deps["yandex"].get_album = AsyncMock(return_value={
        "id": "123", "title": "X", "artists": ["Y"], "year": 2020,
        "track_count": 1, "duration_ms": 60_000,
        "cover_uri": "x/%%",
        "tracks": [{"title": "t", "duration_ms": 60_000}],
    })
    m = _msg("https://music.yandex.ru/album/123")
    await handle_link(m, **deps)
    deps["yandex"].get_album.assert_awaited_once_with("123")
    m.answer_photo.assert_awaited_once()


async def test_artist_link_routes_to_artist(deps):
    deps["yandex"].get_artist = AsyncMock(return_value={
        "id": "789", "name": "Queen", "cover_uri": "x/%%",
        "top_tracks": [{"id": "1", "title": "BR", "duration_ms": 355_000}],
    })
    m = _msg("https://music.yandex.ru/artist/789")
    await handle_link(m, **deps)
    deps["yandex"].get_artist.assert_awaited_once_with("789")


async def test_playlist_link_routes_to_playlist(deps):
    deps["yandex"].get_playlist = AsyncMock(return_value={
        "id": "1001", "owner": "myname", "title": "Mix",
        "track_count": 1, "duration_ms": 60_000,
        "cover_uri": "x/%%",
        "tracks": [{"title": "s", "artists": ["a"], "duration_ms": 60_000}],
    })
    m = _msg("https://music.yandex.ru/users/myname/playlists/1001")
    await handle_link(m, **deps)
    deps["yandex"].get_playlist.assert_awaited_once_with("myname", "1001")
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_link_handler.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `bot/handlers/link.py`**

```python
import asyncio
import logging
from typing import Any

from aiogram import Router, F
from aiogram.types import Message

from bot.keyboards import (
    album_open_keyboard, artist_open_keyboard,
    playlist_open_keyboard, track_keyboard,
)
from bot.renderers._helpers import cover_url
from bot.renderers.album_card import render_album
from bot.renderers.artist_card import render_artist
from bot.renderers.playlist_card import render_playlist
from bot.renderers.track_card import render_track
from bot.services.cache import Cache
from bot.services.link_parser import parse
from bot.services.songlink import SongLinkClient
from bot.services.yandex import YandexMusicClient, YMNotFound, YMUnauthorized

log = logging.getLogger(__name__)
router = Router(name="link")

TTL_TRACK = 7 * 24 * 3600
TTL_ALBUM = 7 * 24 * 3600
TTL_PLAYLIST = 3600
TTL_ARTIST = 24 * 3600
TTL_SONGLINK = 30 * 24 * 3600


@router.message(F.text)
async def handle_link(
    message: Message,
    cache: Cache,
    yandex: YandexMusicClient,
    songlink: SongLinkClient,
) -> None:
    link = parse(message.text or "")
    if not link:
        await message.answer(
            "🤔 Не похоже на ссылку Яндекс.Музыки.\n\n"
            "Поддерживается: track / album / playlist / artist.\n"
            "Шли /help для подробностей."
        )
        return

    try:
        if link.type == "track":
            await _reply_track(message, link.primary_id, cache, yandex, songlink)
        elif link.type == "album":
            await _reply_album(message, link.primary_id, cache, yandex)
        elif link.type == "artist":
            await _reply_artist(message, link.primary_id, cache, yandex)
        elif link.type == "playlist":
            await _reply_playlist(message, link.secondary_id, link.primary_id, cache, yandex)
    except YMNotFound:
        await message.answer("😔 Не найдено или удалено из Яндекс.Музыки.")
    except YMUnauthorized:
        log.error("yandex token unauthorized — bot needs new token")
        await message.answer("⚠️ Сервис временно недоступен. Попробуй позже.")


async def _reply_track(message: Message, track_id: str, cache: Cache, yandex: YandexMusicClient, songlink: SongLinkClient) -> None:
    cached = await cache.get(f"track:{track_id}")
    if cached:
        track = cached["track"]
        links = cached.get("songlinks", {})
    else:
        yandex_url = f"https://music.yandex.ru/track/{track_id}"
        track, links = await asyncio.gather(
            yandex.get_track(track_id),
            songlink.get_links(yandex_url),
        )
        await cache.set(
            f"track:{track_id}",
            {"track": track, "songlinks": links},
            ttl_seconds=TTL_TRACK,
        )

    caption = render_track(track, songlinks=links or None)
    photo = cover_url(track.get("cover_uri"))
    if photo:
        await message.answer_photo(photo, caption=caption, reply_markup=track_keyboard(track_id))
    else:
        await message.answer(caption, reply_markup=track_keyboard(track_id))


async def _reply_album(message: Message, album_id: str, cache: Cache, yandex: YandexMusicClient) -> None:
    cached = await cache.get(f"album:{album_id}")
    album = cached or await yandex.get_album(album_id)
    if not cached:
        await cache.set(f"album:{album_id}", album, ttl_seconds=TTL_ALBUM)

    caption = render_album(album)
    photo = cover_url(album.get("cover_uri"))
    if photo:
        await message.answer_photo(photo, caption=caption, reply_markup=album_open_keyboard(album_id))
    else:
        await message.answer(caption, reply_markup=album_open_keyboard(album_id))


async def _reply_artist(message: Message, artist_id: str, cache: Cache, yandex: YandexMusicClient) -> None:
    cached = await cache.get(f"artist:{artist_id}")
    artist = cached or await yandex.get_artist(artist_id)
    if not cached:
        await cache.set(f"artist:{artist_id}", artist, ttl_seconds=TTL_ARTIST)

    caption = render_artist(artist)
    photo = cover_url(artist.get("cover_uri"))
    if photo:
        await message.answer_photo(photo, caption=caption, reply_markup=artist_open_keyboard(artist_id))
    else:
        await message.answer(caption, reply_markup=artist_open_keyboard(artist_id))


async def _reply_playlist(message: Message, owner: str, kind: str, cache: Cache, yandex: YandexMusicClient) -> None:
    key = f"playlist:{owner}:{kind}"
    cached = await cache.get(key)
    playlist = cached or await yandex.get_playlist(owner, kind)
    if not cached:
        await cache.set(key, playlist, ttl_seconds=TTL_PLAYLIST)

    caption = render_playlist(playlist)
    photo = cover_url(playlist.get("cover_uri"))
    if photo:
        await message.answer_photo(photo, caption=caption, reply_markup=playlist_open_keyboard(owner, kind))
    else:
        await message.answer(caption, reply_markup=playlist_open_keyboard(owner, kind))
```

- [ ] **Step 4: Modify `bot/main.py` to register the router**

In `bot/main.py`, add import:
```python
from bot.handlers import link as link_handler
```

And after `dp.include_router(system.router)`:
```python
dp.include_router(link_handler.router)
```

- [ ] **Step 5: Run tests — verify pass**

```bash
uv run pytest tests/test_link_handler.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/link.py bot/main.py tests/test_link_handler.py
git commit -m "feat(handlers): link router for track/album/artist/playlist with cache"
```

---

## Task 12: Callback handler (similar tracks + drill-down)

**Files:**
- Create: `bot/handlers/callbacks.py`
- Modify: `bot/main.py` — register `callbacks.router`
- Test: `tests/test_callbacks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_callbacks.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from bot.handlers.callbacks import on_similar, on_track_card


def _cb(data: str) -> MagicMock:
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.answer = AsyncMock()
    cb.message = MagicMock(spec=Message)
    cb.message.answer = AsyncMock()
    cb.message.answer_photo = AsyncMock()
    return cb


@pytest.fixture
def deps():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    yandex = MagicMock()
    yandex.get_track = AsyncMock(return_value={
        "id": "456", "title": "Source Track", "artists": ["X"],
        "album_title": "A", "album_year": 2020,
        "duration_ms": 200_000, "genre": None, "cover_uri": "x/%%",
    })
    yandex.get_similar = AsyncMock(return_value=[
        {"id": "1", "title": "Sim 1", "artists": ["A"], "duration_ms": 100_000},
        {"id": "2", "title": "Sim 2", "artists": ["B"], "duration_ms": 120_000},
    ])
    songlink = MagicMock()
    songlink.get_links = AsyncMock(return_value={})
    return {"cache": cache, "yandex": yandex, "songlink": songlink}


async def test_similar_callback_sends_text_list(deps):
    cb = _cb("similar:456")
    await on_similar(cb, **deps)

    deps["yandex"].get_similar.assert_awaited_once_with("456")
    cb.answer.assert_awaited_once()
    cb.message.answer.assert_awaited_once()
    text = cb.message.answer.call_args.args[0]
    assert "Sim 1" in text and "Sim 2" in text
    assert 'href="https://music.yandex.ru/track/1"' in text


async def test_similar_callback_uses_cache(deps):
    deps["cache"].get = AsyncMock(side_effect=[
        {"id": "456", "title": "Cached Source", "artists": ["X"], "album_title": "A",
         "album_year": 2020, "duration_ms": 100_000, "genre": None, "cover_uri": "x/%%"},
        [{"id": "9", "title": "C", "artists": ["Z"], "duration_ms": 90_000}],
    ])
    cb = _cb("similar:456")
    await on_similar(cb, **deps)
    deps["yandex"].get_similar.assert_not_awaited()


async def test_track_card_drilldown_calls_get_track(deps):
    cb = _cb("track_card:9")
    await on_track_card(cb, **deps)

    deps["yandex"].get_track.assert_awaited_once_with("9")
    cb.answer.assert_awaited_once()
    cb.message.answer_photo.assert_awaited_once()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_callbacks.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `bot/handlers/callbacks.py`**

```python
import asyncio
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.keyboards import similar_drilldown_keyboard, track_keyboard
from bot.renderers._helpers import cover_url
from bot.renderers.similar_list import render_similar
from bot.renderers.track_card import render_track
from bot.services.cache import Cache
from bot.services.songlink import SongLinkClient
from bot.services.yandex import YandexMusicClient, YMNotFound

log = logging.getLogger(__name__)
router = Router(name="callbacks")

TTL_TRACK = 7 * 24 * 3600
TTL_SIMILAR = 7 * 24 * 3600


@router.callback_query(F.data.startswith("similar:"))
async def on_similar(
    callback: CallbackQuery,
    cache: Cache,
    yandex: YandexMusicClient,
    songlink: SongLinkClient,
) -> None:
    track_id = callback.data.split(":", 1)[1]

    source = await cache.get(f"track:{track_id}")
    source_track = source["track"] if source and "track" in source else source
    if not source_track:
        try:
            source_track = await yandex.get_track(track_id)
        except YMNotFound:
            await callback.answer("Трек не найден", show_alert=True)
            return

    sim_cached = await cache.get(f"similar:{track_id}")
    if sim_cached is not None:
        similar = sim_cached
    else:
        similar = await yandex.get_similar(track_id)
        await cache.set(f"similar:{track_id}", similar, ttl_seconds=TTL_SIMILAR)

    await callback.answer()

    if not similar:
        await callback.message.answer("😔 Не нашёл похожих треков.")
        return

    text = render_similar(source_title=source_track["title"], tracks=similar)
    keyboard = similar_drilldown_keyboard([t["id"] for t in similar])
    await callback.message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("track_card:"))
async def on_track_card(
    callback: CallbackQuery,
    cache: Cache,
    yandex: YandexMusicClient,
    songlink: SongLinkClient,
) -> None:
    track_id = callback.data.split(":", 1)[1]

    cached = await cache.get(f"track:{track_id}")
    if cached:
        track = cached["track"]
        links = cached.get("songlinks", {})
    else:
        yandex_url = f"https://music.yandex.ru/track/{track_id}"
        try:
            track, links = await asyncio.gather(
                yandex.get_track(track_id),
                songlink.get_links(yandex_url),
            )
        except YMNotFound:
            await callback.answer("Трек не найден", show_alert=True)
            return
        await cache.set(f"track:{track_id}", {"track": track, "songlinks": links}, ttl_seconds=TTL_TRACK)

    await callback.answer()
    caption = render_track(track, songlinks=links or None)
    photo = cover_url(track.get("cover_uri"))
    if photo:
        await callback.message.answer_photo(photo, caption=caption, reply_markup=track_keyboard(track_id))
    else:
        await callback.message.answer(caption, reply_markup=track_keyboard(track_id))
```

- [ ] **Step 4: Modify `bot/main.py` to register the callback router**

Add import:
```python
from bot.handlers import callbacks as callbacks_handler
```

After `dp.include_router(link_handler.router)`:
```python
dp.include_router(callbacks_handler.router)
```

- [ ] **Step 5: Run tests — verify pass**

```bash
uv run pytest tests/test_callbacks.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/callbacks.py bot/main.py tests/test_callbacks.py
git commit -m "feat(callbacks): similar-tracks list + drill-down to full track card"
```

---

## Task 13: Inline query handler

**Files:**
- Create: `bot/handlers/inline.py`
- Modify: `bot/main.py` — register `inline.router`
- Test: `tests/test_inline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_inline.py
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import InlineQuery

from bot.handlers.inline import on_inline_query


def _query(text: str) -> MagicMock:
    q = MagicMock(spec=InlineQuery)
    q.id = "qid"
    q.query = text
    q.answer = AsyncMock()
    return q


@pytest.fixture
def deps():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    yandex = MagicMock()
    yandex.get_track = AsyncMock(return_value={
        "id": "456", "title": "BR", "artists": ["Queen"],
        "album_title": "ANO", "album_year": 1975,
        "duration_ms": 355_000, "genre": "rock",
        "cover_uri": "avatars.yandex.net/x/%%",
    })
    return {"cache": cache, "yandex": yandex}


async def test_inline_track_returns_one_article(deps):
    q = _query("https://music.yandex.ru/album/123/track/456")
    await on_inline_query(q, **deps, inline_timeout=0.8)

    q.answer.assert_awaited_once()
    results = q.answer.call_args.args[0]
    assert len(results) == 1
    article = results[0]
    assert "BR" in article.title
    assert "Queen" in article.title


async def test_inline_invalid_query_returns_hint(deps):
    q = _query("not a url")
    await on_inline_query(q, **deps, inline_timeout=0.8)

    q.answer.assert_awaited_once()
    kwargs = q.answer.call_args.kwargs
    # either empty results list with switch_pm_text, or single hint article — accept either
    results = q.answer.call_args.args[0]
    if results:
        assert any("yandex" in r.title.lower() or "ссылк" in r.title.lower() for r in results)
    else:
        assert kwargs.get("switch_pm_text") or kwargs.get("button")


async def test_inline_uses_cache_on_hit(deps):
    deps["cache"].get = AsyncMock(return_value={
        "track": {"id": "456", "title": "Cached", "artists": ["X"],
                  "album_title": "A", "album_year": 2020, "duration_ms": 100_000,
                  "genre": None, "cover_uri": "x/%%"},
        "songlinks": {},
    })
    q = _query("https://music.yandex.ru/track/456")
    await on_inline_query(q, **deps, inline_timeout=0.8)

    deps["yandex"].get_track.assert_not_awaited()
    q.answer.assert_awaited_once()


async def test_inline_returns_empty_on_timeout(deps):
    async def slow(*a, **kw):
        await asyncio.sleep(2.0)
        return {}
    deps["yandex"].get_track = AsyncMock(side_effect=slow)
    q = _query("https://music.yandex.ru/track/456")
    await on_inline_query(q, **deps, inline_timeout=0.05)

    q.answer.assert_awaited_once()
    results = q.answer.call_args.args[0]
    assert results == []  # empty on timeout
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_inline.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `bot/handlers/inline.py`**

```python
import asyncio
import logging

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from bot.keyboards import track_keyboard
from bot.renderers._helpers import cover_url
from bot.renderers.track_card import render_track
from bot.services.cache import Cache
from bot.services.link_parser import parse
from bot.services.yandex import YandexMusicClient, YMError

log = logging.getLogger(__name__)
router = Router(name="inline")

TTL_TRACK = 7 * 24 * 3600


@router.inline_query()
async def on_inline_query(
    query: InlineQuery,
    cache: Cache,
    yandex: YandexMusicClient,
    inline_timeout: float = 0.8,
) -> None:
    link = parse(query.query)
    if not link or link.type != "track":
        # only tracks supported in inline (most common share scenario)
        await query.answer(
            results=[],
            cache_time=10,
            is_personal=True,
        )
        return

    track_id = link.primary_id
    try:
        track = await asyncio.wait_for(
            _get_track(track_id, cache, yandex),
            timeout=inline_timeout,
        )
    except (asyncio.TimeoutError, YMError) as e:
        log.warning("inline lookup failed for %s: %s", track_id, e)
        await query.answer(results=[], cache_time=5, is_personal=True)
        return

    caption = render_track(track)
    thumb = cover_url(track.get("cover_uri"), size="200x200")

    article = InlineQueryResultArticle(
        id=track_id,
        title=f"🎵 {track['title']} — {', '.join(track['artists'])}",
        description=f"{track['album_title']} · {_fmt(track['duration_ms'])}",
        thumbnail_url=thumb,
        input_message_content=InputTextMessageContent(
            message_text=caption + "\n\n💡 Open in DM for cross-platform links",
            parse_mode="HTML",
        ),
        reply_markup=track_keyboard(track_id),
    )
    await query.answer(results=[article], cache_time=300, is_personal=False)


async def _get_track(track_id: str, cache: Cache, yandex: YandexMusicClient) -> dict:
    cached = await cache.get(f"track:{track_id}")
    if cached and "track" in cached:
        return cached["track"]
    track = await yandex.get_track(track_id)
    await cache.set(f"track:{track_id}", {"track": track, "songlinks": {}}, ttl_seconds=TTL_TRACK)
    return track


def _fmt(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"
```

- [ ] **Step 4: Modify `bot/main.py` to register the inline router and pass timeout**

Add import:
```python
from bot.handlers import inline as inline_handler
```

After `dp.include_router(callbacks_handler.router)`:
```python
dp["inline_timeout"] = settings.inline_timeout
dp.include_router(inline_handler.router)
```

- [ ] **Step 5: Run tests — verify pass**

```bash
uv run pytest tests/test_inline.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/inline.py bot/main.py tests/test_inline.py
git commit -m "feat(inline): inline-query handler with hard timeout for sub-1s response"
```

---

## Task 14: Middlewares (rate limit + global error catcher)

**Files:**
- Create: `bot/middlewares.py`
- Modify: `bot/main.py` — wire middlewares
- Test: `tests/test_middlewares.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_middlewares.py
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, User

from bot.middlewares import RateLimitMiddleware, ErrorMiddleware


def _msg_event(user_id: int = 1) -> MagicMock:
    m = MagicMock(spec=Message)
    m.from_user = MagicMock(spec=User)
    m.from_user.id = user_id
    m.answer = AsyncMock()
    return m


async def test_rate_limit_allows_first_n_requests():
    mw = RateLimitMiddleware(per_minute=3)
    handler = AsyncMock(return_value="ok")
    event = _msg_event()
    for _ in range(3):
        result = await mw(handler, event, {})
        assert result == "ok"
    assert handler.await_count == 3


async def test_rate_limit_blocks_excess():
    mw = RateLimitMiddleware(per_minute=2)
    handler = AsyncMock(return_value="ok")
    event = _msg_event()
    await mw(handler, event, {})
    await mw(handler, event, {})
    await mw(handler, event, {})  # this one blocked
    assert handler.await_count == 2
    event.answer.assert_awaited()
    assert "🐢" in event.answer.call_args.args[0] or "быстро" in event.answer.call_args.args[0].lower()


async def test_rate_limit_per_user_independent():
    mw = RateLimitMiddleware(per_minute=1)
    handler = AsyncMock(return_value="ok")
    a = _msg_event(user_id=1)
    b = _msg_event(user_id=2)
    await mw(handler, a, {})
    await mw(handler, b, {})  # different user, allowed
    assert handler.await_count == 2


async def test_error_middleware_catches_and_replies():
    mw = ErrorMiddleware()
    async def boom(event, data):
        raise RuntimeError("kaboom")
    event = _msg_event()
    await mw(boom, event, {})
    event.answer.assert_awaited()
    assert "пошло не так" in event.answer.call_args.args[0].lower() or "ошибка" in event.answer.call_args.args[0].lower()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_middlewares.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `bot/middlewares.py`**

```python
import logging
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

log = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, per_minute: int = 10):
        self._limit = per_minute
        self._window = 60.0
        self._buckets: dict[int, deque[float]] = defaultdict(deque)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        now = time.monotonic()
        bucket = self._buckets[user.id]
        while bucket and now - bucket[0] > self._window:
            bucket.popleft()

        if len(bucket) >= self._limit:
            if isinstance(event, Message):
                await event.answer("🐢 Слишком быстро, подожди немного.")
            return None

        bucket.append(now)
        return await handler(event, data)


class ErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            log.exception("unhandled error in handler")
            if isinstance(event, Message):
                try:
                    await event.answer("⚠️ Что-то пошло не так. Уже разбираемся.")
                except Exception:
                    log.exception("failed to send error message")
            return None
```

- [ ] **Step 4: Wire middlewares in `bot/main.py`**

After Dispatcher creation:
```python
from bot.middlewares import ErrorMiddleware, RateLimitMiddleware

dp.message.middleware(ErrorMiddleware())
dp.message.middleware(RateLimitMiddleware(per_minute=settings.rate_limit_per_minute))
dp.callback_query.middleware(ErrorMiddleware())
```

- [ ] **Step 5: Run tests — verify pass**

```bash
uv run pytest tests/test_middlewares.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add bot/middlewares.py bot/main.py tests/test_middlewares.py
git commit -m "feat(middleware): per-user rate limit + global error catcher"
```

---

## Task 15: Docker + docker-compose

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache-dir \
    "aiogram>=3.13,<4" \
    "yandex-music>=2.2.0" \
    "httpx>=0.27" \
    "redis>=5.0" \
    "pydantic-settings>=2.5"

COPY bot/ ./bot/

RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

CMD ["python", "-m", "bot.main"]
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    depends_on:
      redis:
        condition: service_healthy

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --maxmemory 128mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  redis_data:
```

- [ ] **Step 3: Write `.dockerignore`**

```
.git
.venv
__pycache__
*.pyc
.pytest_cache
.idea
.vscode
docs/
tests/
.env
.env.example
```

- [ ] **Step 4: Local smoke test**

```bash
# build only (no actual run since we don't have a real token to test polling)
docker compose build
```

Expected: build succeeds, no errors.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "build: Dockerfile + compose with Redis service and healthcheck"
```

---

## Task 16: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# Yandex.Music Telegram Bot

Telegram bot that takes a Yandex.Music link (track / album / playlist / artist) and replies with a rich card — title, artist, duration, cover image, and cross-platform links to Spotify / Apple Music / YouTube Music.

**Live bot:** [@your_bot_handle](https://t.me/your_bot_handle)

## Features

- 🎵 **Track cards** with cover image, metadata, and cross-platform links
- 💿 **Albums / playlists / artists** support
- 🔗 **song.link integration** — instantly find the track on Spotify / Apple Music / YouTube Music
- 🎯 **Similar tracks** — one tap finds 5 related songs with drill-down to full cards
- ⚡ **Inline mode** — `@your_bot_handle <link>` works in any chat without adding the bot
- 🚀 **Redis caching** — repeat queries answer in <50 ms

## Stack

- **Python 3.12** + **aiogram 3.x** (async Telegram bot framework)
- **yandex-music** PyPI library for Yandex.Music API access
- **httpx** for song.link HTTP calls
- **Redis 7** for response caching (TTL-based, LRU-eviction, 128 MB cap)
- **Docker Compose** for deployment
- **pytest** + `respx` + `fakeredis` for tests (no real API calls in CI)

## Architectural decisions

| Decision | Why |
|---|---|
| **Polling, not webhooks** | Simpler — no public HTTPS/cert needed, fits a single-VPS deploy |
| **Docker Compose** | Ships Redis alongside the bot in one `up -d`. Easy rollback |
| **Read-through Redis cache** | Inline mode needs sub-1s response; Yandex.Music API is 500-1500 ms |
| **Mock external APIs in tests** | Tests stay fast, deterministic, and don't burn the Yandex token |
| **Pure-function renderers** | Caption-formatting logic is unit-testable without bot framework |
| **Thin handlers** | All business logic in services — handlers just route. Easier to add new entry points (e.g., webhook) |

## Run locally

```bash
git clone <repo-url>
cd yandex-music-bot
cp .env.example .env
# fill in TELEGRAM_BOT_TOKEN and YANDEX_MUSIC_TOKEN in .env
docker compose up -d --build
docker compose logs -f bot
```

To get a Yandex.Music token, see [yandex-music README](https://github.com/MarshalX/yandex-music-api#получение-токена).

## Run tests

```bash
uv sync
uv run pytest
```

## Project structure

```
bot/
├── main.py            # entrypoint: builds Bot+Dispatcher, starts polling
├── config.py          # pydantic-settings reads .env
├── handlers/          # thin aiogram routers (system, link, callbacks, inline)
├── services/          # LinkParser, YandexMusicClient, SongLinkClient, Cache
├── renderers/         # pure functions: dict → HTML caption
├── keyboards.py       # InlineKeyboard factories
└── middlewares.py     # rate-limit + global error catcher

tests/                 # one test module per source module, all external APIs mocked
docs/superpowers/      # design spec + this implementation plan
docker-compose.yml
Dockerfile
```

## Roadmap

Things considered for the MVP and deferred (each is a few hours of work):

- 🎵 **30-second preview audio** — legal alternative to full MP3, plays inline in Telegram
- 📜 **Lyrics on demand** — `yandex-music` exposes lyrics for most tracks
- 📊 **`/history` per user** — last 10 lookups, Redis-backed
- 📈 **`/stats` admin command** — request count, top tracks, cache hit rate
- 🌐 **i18n (ru/en)** — switch by `language_code`
- 🎯 **Personalized recommendations** based on user history
````

- [ ] **Step 2: Verify markdown renders correctly**

```bash
cat README.md | head -20
```

Expected: looks readable.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README with stack, decisions, run instructions, roadmap"
```

---

## Final verification

- [ ] **Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Build Docker image**

```bash
docker compose build
```

Expected: build succeeds.

- [ ] **Local smoke run** (after filling `.env` with real tokens)

```bash
docker compose up -d
docker compose logs -f bot
# in Telegram, find your bot via @BotFather, send /ping → bot replies "pong"
# send a Yandex.Music link → bot replies with card
```

- [ ] **Deploy to VPS**

```bash
# on VPS
git clone <repo-url> && cd yandex-music-bot
cp .env.example .env
# paste real tokens
docker compose up -d --build
docker compose ps   # verify both services Up
```

- [ ] **Enable inline mode in @BotFather**

```
/setinline → @your_bot → "Send me a Yandex.Music link"
```

- [ ] **Final sanity test in Telegram**
  - DM: `/start`, `/help`, `/ping` all respond correctly
  - DM: track / album / artist / playlist links produce cards
  - DM: tap "🎯 Похожие треки" → list appears, tap "1️⃣" → full card
  - In any chat: type `@your_bot https://music.yandex.ru/track/X` → preview appears in dropdown, tap → posts as your message

---

## Notes for the implementer

- **Yandex.Music token caveat:** the library reads sensitive cookies. Generate the token once via the [official guide](https://github.com/MarshalX/yandex-music-api#получение-токена) and never commit it.
- **Handling `yandex-music` lib quirks:** the lib is sync. We always wrap calls with `asyncio.to_thread` (already done in `YandexMusicClient`). Don't call sync methods directly from coroutines.
- **Rate limit numbers** are conservative defaults (10 req/min). If the bot gets popular, raise via `.env`.
- **song.link free tier** is 60 req/min — more than enough given Redis cache (`songlink:` keys live 30 days).
- **HTML escaping:** all dynamic strings in renderers go through `html_escape()`. Never f-string raw input into HTML caption.
- **If a test fails on Windows due to encoding:** ensure git is configured `core.autocrlf=true` and that pytest output uses UTF-8 (`PYTHONIOENCODING=utf-8`).
