# Yandex.Music Telegram Bot — Design Spec

**Date:** 2026-04-25
**Status:** Approved by user, ready for implementation planning
**Context:** Test task — Telegram bot that accepts Yandex.Music links and returns track info, plus a curated set of "wow-factor" features to differentiate from a minimal solution.

---

## 1. Goal

Build a Telegram bot that:

1. **Core requirement** — accepts a Yandex.Music link and returns title, artist, duration.
2. **Differentiators** — visually polished cards, cross-platform links, support for multiple link types, inline mode, similar-track discovery, Redis caching for sub-second responses.
3. **Hosting** — runs on user's VPS (Ubuntu 22.04, 2 GB RAM, 20 GB NVMe) via Docker Compose. Available 24/7 to satisfy "random checks 11–19" requirement, with the "local server" bonus from the task description.

## 2. Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.12 | Best library support for Yandex.Music |
| Bot framework | aiogram 3.x | Modern async, idiomatic Python, strong inline-mode support |
| Yandex.Music client | `yandex-music` (PyPI) | Most mature unofficial library, returns rich metadata |
| Cross-platform links | song.link API (free tier, 60 req/min) | Single endpoint returns Spotify / Apple Music / YouTube Music URLs |
| Cache | Redis 7-alpine | TTL-based, eviction policy `allkeys-lru`, 128 MB cap |
| Packaging | Docker + docker-compose | Reproducible deploy, Redis ships in same compose file, easy rollback |
| Dependency mgmt | `uv` (or `poetry` as fallback) | Fast install, lockfile |
| Tests | `pytest` + `aiogram` test utilities | Mock Yandex client, no real API calls in tests |

## 3. Feature Set (MVP)

| # | Feature | Description |
|---|---|---|
| F1 | Track card | Cover image + caption with title, artist, album, year, duration, genre. HTML-formatted. |
| F2 | Cross-platform links | Spotify / Apple Music / YouTube Music links via song.link, embedded in caption. |
| F3 | Album / Playlist / Artist support | Bot detects link type and renders appropriate card (album with tracklist, artist with top-5, playlist with first 10). |
| F4 | Inline mode | `@bot <yandex_url>` works in any chat without adding the bot. Returns clickable card preview that posts as the user's own message. |
| F5 | Similar tracks | Inline button "🎯 Похожие треки" → text list with hyperlinks + optional drill-down buttons (1️⃣–5️⃣) for full card of any item. |
| F6 | Redis cache | Read-through cache for all Yandex.Music + song.link responses. Sub-50ms repeat queries. Graceful degradation if Redis is down. |

**Explicitly NOT in MVP:**
- ❌ MP3 download (DRM/legal risk + risk of token ban during evaluation)
- ❌ Lyrics (deferred to backlog)
- ❌ User history / `/stats` (deferred to backlog)
- ❌ i18n (deferred to backlog)

## 4. Architecture

### Layers

```
┌────────────────────────────────────────────────────┐
│  Telegram BotAPI ←→ aiogram Router (handlers)      │  UI
├────────────────────────────────────────────────────┤
│  Service layer:                                     │
│    • LinkParser (URL → {type, id})                  │
│    • YandexMusicClient (wraps `yandex-music` lib)   │
│    • SongLinkClient (HTTP → song.link API)          │
│    • CardRenderer (formats caption + keyboard)      │
├────────────────────────────────────────────────────┤
│  Cache layer (Redis): TTL'd JSON keyed by URL/ID    │
└────────────────────────────────────────────────────┘
```

**Principle:** handlers are thin (parse update → call services → reply). All Yandex.Music logic is isolated in `YandexMusicClient` so it's mockable in tests and replaceable if we ever switch source.

### File structure

```
yandex-music-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py                  # entrypoint, Dispatcher setup, polling loop
│   ├── config.py                # pydantic-settings reads .env
│   ├── handlers/
│   │   ├── start.py             # /start, /help, /ping
│   │   ├── link.py              # message handler for Yandex links in DM/groups
│   │   ├── inline.py            # inline_query handler
│   │   └── callbacks.py         # callback_query handler ("similar:X", "track_card:X")
│   ├── services/
│   │   ├── link_parser.py       # URL → ParsedLink | None
│   │   ├── yandex.py            # YandexMusicClient
│   │   ├── songlink.py          # SongLinkClient (httpx async)
│   │   └── cache.py             # Redis wrapper with JSON serde + fallback
│   ├── renderers/
│   │   ├── track_card.py
│   │   ├── album_card.py
│   │   ├── artist_card.py
│   │   ├── playlist_card.py
│   │   └── similar_list.py
│   ├── keyboards.py             # InlineKeyboardBuilder for all replies
│   └── middlewares.py           # rate limit, error catching, logging
├── tests/
│   ├── test_link_parser.py
│   ├── test_renderers.py
│   ├── test_cache.py
│   └── test_handlers.py
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

## 5. User Flows

### Flow A — track link in DM/group

```
User → "https://music.yandex.ru/album/123/track/456"
  ↓
LinkParser → {type: "track", track_id: "456", album_id: "123"}
  ↓
Cache.get("track:456") → MISS
  ↓
YandexMusicClient.get_track(456)        ← parallel
SongLinkClient.get_links(yandex_url)    ← parallel (timeout 2s)
  ↓
Cache.set("track:456", payload, TTL=7d)
  ↓
CardRenderer.render_track(track, links)
  ↓
bot.send_photo(cover_url, caption, reply_markup=keyboard)
```

**Caption template:**
```
🎵 Bohemian Rhapsody
👤 Queen
💿 A Night at the Opera (1975)
⏱ 5:55 · 🎼 Rock

🔗 Other platforms: Spotify · Apple Music · YouTube Music
```

**Keyboard:**
- `🎯 Похожие треки` (callback `similar:456`)
- `▶️ Открыть в Яндекс.Музыке` (URL button, deep link)

### Flow B — album / playlist / artist

LinkParser routes by URL pattern:

| URL pattern | Type | Response |
|---|---|---|
| `.../album/X/track/Y` | track | Flow A |
| `.../album/X` | album | cover + caption with up to 15 tracks |
| `.../users/U/playlists/P` | playlist | cover + caption with first 10 tracks |
| `.../artist/X` | artist | photo + top-5 tracks + "Discography" button |
| anything else | unknown | "не поддерживается, шли track / album / playlist / artist" |

### Flow C — Inline mode

```
User types in any chat: @bot https://music.yandex.ru/album/123/track/456
  ↓
InlineQuery(query="<url>")
  ↓
LinkParser.parse(query) → ParsedLink
  ↓
Cache.get(...) OR fetch with 800ms hard timeout
  ↓
answer_inline_query([
    InlineQueryResultArticle(
        title, description, thumb_url=cover,
        input_message_content=card_html,
        reply_markup=keyboard
    )
])
```

**Inline-specific constraints:**
- Hard timeout 800ms total (Telegram closes the dropdown if response > 1s).
- Cross-platform links **skipped** in inline (they add ~500ms via song.link). Card in inline shows `Open in DM for cross-platform links`.
- If query doesn't look like a Yandex.Music URL → empty result list + "Send a Yandex.Music link" hint.

### Flow D — Similar tracks button

```
User taps "🎯 Похожие треки"
  ↓
CallbackQuery(data="similar:<track_id>")
  ↓
Cache.get("similar:<track_id>") OR fetch from Yandex
  ↓
Single message with hyperlinked text list:
  🎯 Похожие на «Bohemian Rhapsody»:
  1. <a>Stairway to Heaven</a> — Led Zeppelin · 8:02
  2. <a>Hotel California</a> — Eagles · 6:30
  3. ...
  ↓
Optional row of 5 buttons [1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣]
  → tap = render full card for that track (callback "track_card:<id>")
```

**Why a single message (not 5 cards):** avoids spam, gives overview at a glance, drill-down is opt-in.

## 6. Data Layer (Redis)

### Why cache

1. Inline mode needs <1s response — Redis hit is <50ms vs. Yandex API 500–1500ms.
2. Yandex.Music token can be rate-limited under flood — cache absorbs repeats.
3. song.link free tier is 60 req/min — cache makes us comfortably stay under.

### Key schema

| Key | Value | TTL | Rationale |
|---|---|---|---|
| `track:{id}` | JSON: title, artist, album, duration, cover_uri, genre, year | 7 days | Tracks rarely change |
| `album:{id}` | JSON: meta + tracklist | 7 days | Static after release |
| `playlist:{owner}:{id}` | JSON: meta + tracks | 1 hour | User playlists mutate |
| `artist:{id}` | JSON: meta + top-5 tracks | 1 day | Top-tracks chart shifts |
| `similar:{track_id}` | JSON: list of 5 similar tracks | 7 days | Yandex algorithm is stable |
| `songlink:{sha1(yandex_url)}` | JSON: platform → URL map | 30 days | External URLs are very stable |

### Strategy

- **Read-through:** handler always checks cache first, on MISS fetches and writes back.
- **Serialization:** `json.dumps`/`json.loads` over plain dicts. Upgrade to `pydantic.model_dump_json()` only if model complexity demands it.
- **Invalidation:** TTL only. No manual refresh in MVP.
- **Cache stampede:** not protected against — out of scope for test task scale.

### Failure mode

Redis down → log warning, fall back to direct fetch. The cache is an optimization, not a source of truth. Bot remains fully functional, just slower.

```python
async def get_track(track_id):
    try:
        if cached := await cache.get(f"track:{track_id}"):
            return cached
    except RedisError:
        log.warning("cache unavailable, falling back to direct fetch")
    return await yandex_client.get_track(track_id)
```

## 7. Error Handling

| Scenario | Action | User-facing message |
|---|---|---|
| URL doesn't parse | LinkParser returns `None` | "🤔 Не похоже на ссылку Яндекс.Музыки. Поддерживается track / album / playlist / artist" |
| Track not found (404) | catch `NotFoundError` | "😔 Трек не найден или удалён" |
| Yandex token expired/banned | catch `Unauthorized` | "⚠️ Сервис временно недоступен" + ERROR log |
| song.link timeout / 5xx | swallow, render card without cross-platform row | (silent degrade) |
| Redis down | catch `RedisError`, fallback to direct fetch | (silent degrade) |
| Unhandled exception | global aiogram error middleware | "⚠️ Что-то пошло не так" + traceback to log |
| Flood (>10 req/min per user) | rate-limit middleware | "🐢 Слишком быстро, подожди немного" |

**Principle:** no external failure terminates the process. Bot always replies with something meaningful.

## 8. Logging

- `logging` stdlib with JSON formatter (or `structlog` if preferred).
- Levels: INFO for business events (request received, cache hit/miss), WARNING for degradations, ERROR for exceptions.
- All logs to stdout → `docker compose logs -f bot`.

## 9. Deployment

### docker-compose.yml (sketch)

```yaml
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    depends_on: [redis]

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes: [redis_data:/data]
    command: redis-server --maxmemory 128mb --maxmemory-policy allkeys-lru

volumes:
  redis_data:
```

### Dockerfile (sketch)

- Base: `python:3.12-slim`
- Use `uv` for fast dep install
- Non-root user (`appuser`)
- `CMD ["python", "-m", "bot.main"]`

### Deploy on VPS

```bash
# initial
git clone <repo> && cd yandex-music-bot
cp .env.example .env  # paste tokens
docker compose up -d --build

# updates
git pull && docker compose up -d --build
```

### Health check

`/ping` command returns "pong" — manual sanity check during random evaluation hours.

## 10. Testing

| File | Scope |
|---|---|
| `test_link_parser.py` | All URL variants: track, album, playlist, artist, malformed, with `?utm_*` tracking, short forms `music.yandex.ru/track/X` |
| `test_renderers.py` | Caption assembly from mock track/album objects. HTML escaping (track named `<script>` doesn't break) |
| `test_cache.py` | JSON serde, fallback path when Redis raises |
| `test_handlers.py` | Mock `YandexMusicClient`, push update through dispatcher, assert `send_photo` called with expected caption + keyboard. Inline-query timeout path. |

**Out of scope:**
- Real Yandex.Music API (flaky, requires token, slow) — always mocked.
- Real Telegram BotAPI — use `aiogram` test utilities.
- Coverage target: ~70%, focus on critical logic.

**No CI** for the test task — local `pytest` is enough.

## 11. README (for reviewer)

Sections:
1. What the bot does + Telegram link `@your_bot_handle`
2. Screenshots of cards (track / album / inline preview)
3. Stack & architectural decisions (why Docker, why Redis, why aiogram 3)
4. Run locally (3 commands)
5. Project structure with one-line description per folder
6. Roadmap / next steps — backlog features (lyrics, history, `/stats`, i18n) to demonstrate broader thinking

## 12. Out of Scope (Backlog)

Captured here so they're not lost — to be mentioned in README "Roadmap":

- 🎵 30-second preview audio (legal alternative to full MP3)
- 📜 Lyrics on demand
- 📊 `/history` per user (Redis-backed)
- 📈 `/stats` for admin (request count, top tracks, cache hit rate)
- 🌐 i18n (ru/en based on `language_code`)
- 🎯 Recommendations based on user history
