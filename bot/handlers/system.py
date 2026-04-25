from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.keyboards import similar_drilldown_keyboard
from bot.renderers.similar_list import render_similar
from bot.services.cache import Cache
from bot.services.yandex import YMNotFound, YandexMusicClient

router = Router(name="system")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    cache: Cache | None = None,
    yandex: YandexMusicClient | None = None,
) -> None:
    payload = _start_payload(message.text)
    if payload.startswith("similar_") and cache is not None and yandex is not None:
        await _handle_similar_start(message, payload.removeprefix("similar_"), cache, yandex)
        return

    handle = "@your_bot"
    bot = getattr(message, "bot", None)
    if bot is not None:
        try:
            me = await bot.get_me()
        except Exception:
            me = None
        if me and getattr(me, "username", None):
            handle = f"@{me.username}"

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


def _start_payload(text: str | None) -> str:
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return ""
    return parts[1].strip()


async def _handle_similar_start(
    message: Message,
    track_id: str,
    cache: Cache,
    yandex: YandexMusicClient,
) -> None:
    source = await cache.get(f"track:{track_id}")
    source_track = source["track"] if source and "track" in source else source
    if not source_track:
        try:
            source_track = await yandex.get_track(track_id)
        except YMNotFound:
            await message.answer("😔 Трек не найден или удалён из Яндекс.Музыки.")
            return

    similar = await cache.get(f"similar:{track_id}")
    if similar is None:
        similar = await yandex.get_similar(track_id)
        await cache.set(f"similar:{track_id}", similar, ttl_seconds=7 * 24 * 3600)

    if not similar:
        await message.answer("😔 Не нашёл похожих треков.")
        return

    text = render_similar(source_title=source_track["title"], tracks=similar)
    keyboard = similar_drilldown_keyboard([track["id"] for track in similar])
    await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
