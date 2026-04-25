# Telegram-бот для Яндекс.Музыки

Telegram-бот, который принимает ссылку на Яндекс.Музыку (`track / album / playlist / artist`) и возвращает карточку с информацией: название, артист, длительность, обложка и ссылки на другие музыкальные платформы.

Ссылка на бота: https://t.me/Yandex_botik_bot

## Возможности

- карточки треков с обложкой, метаданными и внешними ссылками
- поддержка альбомов, артистов и плейлистов
- интеграция с `song.link` для Spotify / Apple Music / YouTube Music / Deezer / TIDAL / Amazon Music
- похожие треки с переходом в полную карточку
- inline-режим: `@Yandex_botik_bot <ссылка>` в любом чате
- Redis-кэш для ускорения повторных запросов

## Стек

- Python 3.14 локально, Python 3.14 в Docker
- aiogram 3.x
- yandex-music
- httpx
- Redis 7
- Docker Compose
- pytest + respx + fakeredis

## Архитектурные решения

| Решение | Почему |
|---|---|
| Polling, а не webhooks | Для тестового задания это проще в деплое на VPS |
| Docker Compose | Бот и Redis поднимаются одной командой |
| Read-through Redis cache | Повторные запросы быстрее и меньше нагрузка на внешние API |
| Моки внешних API в тестах | Тесты остаются быстрыми и предсказуемыми |
| Отдельные renderers | Форматирование карточек проще тестировать |
| Thin handlers | Бизнес-логика вынесена в services |

## Локальный запуск

```bash
git clone <repo-url>
cd yandex-music-bot
cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN и YANDEX_MUSIC_TOKEN
python -m uv sync
python -m uv run python -m bot.main
```

Получение токена Яндекс.Музыки:

```bash
python -m uv run python scripts/get_yandex_token.py
```

## Запуск через Docker

```bash
cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN и YANDEX_MUSIC_TOKEN
docker compose up -d --build
docker compose logs -f bot
```

## Примечания по продакшену

- бот развёрнут на VPS и работает через Docker Compose
- Redis не обязателен для локальной разработки, но желателен для стабильной работы и снижения нагрузки на внешние API
- если `song.link` не находит соответствие для трека, бот всё равно возвращает основную карточку без блока внешних ссылок

## Запуск тестов

```bash
python -m uv run pytest -v
```

## Структура проекта

```text
bot/
├── main.py            # bootstrap бота и wiring зависимостей
├── config.py          # конфигурация через pydantic-settings
├── handlers/          # system, link, callbacks, inline
├── services/          # parser, cache, YandexMusic, song.link
├── renderers/         # HTML-карточки
├── keyboards.py       # inline-клавиатуры
└── middlewares.py     # rate limiting и error handling

tests/                 # unit-тесты модулей и handlers
docs/superpowers/      # дизайн и план реализации
docker-compose.yml
Dockerfile
```

## Что можно улучшить дальше

- 30-second preview audio
- lyrics on demand
- `/history` по пользователю
- `/stats` для администратора
- i18n (ru/en)
- персонализированные рекомендации
