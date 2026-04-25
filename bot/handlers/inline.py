import asyncio
import logging

from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

from bot.keyboards import inline_track_keyboard
from bot.renderers._helpers import cover_url, format_duration
from bot.renderers.track_card import render_track
from bot.services.cache import Cache
from bot.services.link_parser import parse
from bot.services.yandex import YMError, YandexMusicClient

log = logging.getLogger(__name__)
router = Router(name="inline")

TTL_TRACK = 7 * 24 * 3600


@router.inline_query()
async def on_inline_query(
    query: InlineQuery,
    cache: Cache,
    yandex: YandexMusicClient,
    bot_username: str | None = None,
    inline_timeout: float = 0.8,
) -> None:
    link = parse(query.query)
    if not link or link.type != "track":
        await query.answer(results=[], cache_time=10, is_personal=True)
        return

    track_id = link.primary_id
    try:
        track = await asyncio.wait_for(_get_track(track_id, cache, yandex), timeout=inline_timeout)
    except (asyncio.TimeoutError, YMError) as exc:
        log.warning("inline lookup failed for %s: %s", track_id, exc)
        await query.answer(results=[], cache_time=5, is_personal=True)
        return

    caption = render_track(track)
    thumb = cover_url(track.get("cover_uri"), size="200x200")
    username = bot_username
    if not username:
        me = await query.bot.get_me()
        username = me.username
    article = InlineQueryResultArticle(
        id=track_id,
        title=f"🎵 {track['title']} — {', '.join(track['artists'])}",
        description=f"{track['album_title']} · {format_duration(track['duration_ms'])}",
        thumbnail_url=thumb,
        input_message_content=InputTextMessageContent(
            message_text=caption + "\n\n💡 Open in DM for cross-platform links",
            parse_mode="HTML",
        ),
        reply_markup=inline_track_keyboard(track_id, username),
    )
    await query.answer(results=[article], cache_time=300, is_personal=False)


async def _get_track(track_id: str, cache: Cache, yandex: YandexMusicClient) -> dict:
    cached = await cache.get(f"track:{track_id}")
    if cached and "track" in cached:
        return cached["track"]

    track = await yandex.get_track(track_id)
    await cache.set(f"track:{track_id}", {"track": track, "songlinks": {}}, ttl_seconds=TTL_TRACK)
    return track
