import asyncio
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards import similar_drilldown_keyboard, track_keyboard
from bot.renderers._helpers import cover_url
from bot.renderers.similar_list import render_similar
from bot.renderers.track_card import render_track
from bot.services.cache import Cache
from bot.services.songlink import SongLinkClient
from bot.services.yandex import YMNotFound, YandexMusicClient

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
    del songlink
    track_id = callback.data.split(":", 1)[1]

    source = await cache.get(f"track:{track_id}")
    source_track = source["track"] if source and "track" in source else source
    if not source_track:
        try:
            source_track = await yandex.get_track(track_id)
        except YMNotFound:
            await callback.answer("Трек не найден", show_alert=True)
            return

    similar = await cache.get(f"similar:{track_id}")
    if similar is None:
        similar = await yandex.get_similar(track_id)
        await cache.set(f"similar:{track_id}", similar, ttl_seconds=TTL_SIMILAR)

    await callback.answer()

    if not similar:
        await callback.message.answer("😔 Не нашёл похожих треков.")
        return

    text = render_similar(source_title=source_track["title"], tracks=similar)
    keyboard = similar_drilldown_keyboard([track["id"] for track in similar])
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
