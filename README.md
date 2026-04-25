# Yandex.Music Telegram Bot

Telegram bot that takes a Yandex.Music link (track / album / playlist / artist) and replies with a rich card: title, artist, duration, cover image, and cross-platform links to multiple music platforms.

Live bot: https://t.me/Yandex_botik_bot

## Features

- Track cards with cover image, metadata, and cross-platform links
- Albums / playlists / artists support
- song.link integration for Spotify / Apple Music / YouTube Music / Deezer / TIDAL / Amazon Music
- Similar tracks with drill-down into full cards
- Inline mode: `@Yandex_botik_bot <link>` in any chat
- Redis caching for fast repeated lookups

## Stack

- Python 3.12 in Docker, Python 3.14 supported for local development
- aiogram 3.x
- yandex-music
- httpx
- Redis 7
- Docker Compose
- pytest + respx + fakeredis

## Architectural decisions

| Decision | Why |
|---|---|
| Polling, not webhooks | Simpler VPS deployment for a test task |
| Docker Compose | Bot and Redis come up together in one command |
| Read-through Redis cache | Faster repeated requests and safer external rate limits |
| Mock external APIs in tests | Deterministic, fast test suite |
| Pure renderers | Formatting logic is easy to unit-test |
| Thin handlers | Business logic stays in services |

## Run locally

```bash
git clone <repo-url>
cd yandex-music-bot
cp .env.example .env
# fill TELEGRAM_BOT_TOKEN and YANDEX_MUSIC_TOKEN
python -m uv sync
python -m uv run python -m bot.main
```

To get a Yandex.Music token:

```bash
python -m uv run python scripts/get_yandex_token.py
```

## Run with Docker

```bash
cp .env.example .env
# fill TELEGRAM_BOT_TOKEN and YANDEX_MUSIC_TOKEN
docker compose up -d --build
docker compose logs -f bot
```

## Production notes

- The bot is deployed on a VPS and runs with Docker Compose.
- Redis is optional for local development, but recommended for stable production behaviour and lower external API load.
- If song.link has no mapping for a track, the bot still returns the main card without cross-platform links.

## Run tests

```bash
python -m uv run pytest -v
```

## Project structure

```text
bot/
├── main.py            # bot bootstrap and dependency wiring
├── config.py          # pydantic-settings config
├── handlers/          # system, link, callbacks, inline
├── services/          # parser, cache, YandexMusic, song.link
├── renderers/         # HTML captions
├── keyboards.py       # inline keyboards
└── middlewares.py     # rate limiting and error handling

tests/                 # unit tests for modules and handlers
docs/superpowers/      # design spec and implementation plan
docker-compose.yml
Dockerfile
```

## Roadmap

- 30-second preview audio
- Lyrics on demand
- `/history` per user
- `/stats` for admin
- i18n (ru/en)
- Personalized recommendations
