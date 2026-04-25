import asyncio
import logging

from aiogram import F, Router
from aiogram.types import Message

from bot.keyboards import (
    album_open_keyboard,
    artist_open_keyboard,
    playlist_open_keyboard,
    track_keyboard,
)
from bot.renderers._helpers import cover_url
from bot.renderers.album_card import render_album
from bot.renderers.artist_card import render_artist
from bot.renderers.playlist_card import render_playlist
from bot.renderers.track_card import render_track
from bot.services.cache import Cache
from bot.services.link_parser import parse
from bot.services.songlink import SongLinkClient
from bot.services.yandex import YMNotFound, YMTemporaryUnavailable, YMUnauthorized, YandexMusicClient

log = logging.getLogger(__name__)
router = Router(name="link")

TTL_TRACK = 7 * 24 * 3600
TTL_ALBUM = 7 * 24 * 3600
TTL_PLAYLIST = 3600
TTL_ARTIST = 24 * 3600
TTL_PLAYLIST_UUID_ALIAS = 24 * 3600


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
            await _reply_track(message, link.primary_id, link.secondary_id, cache, yandex, songlink)
        elif link.type == "album":
            await _reply_album(message, link.primary_id, cache, yandex)
        elif link.type == "artist":
            await _reply_artist(message, link.primary_id, cache, yandex)
        elif link.type == "playlist":
            if link.secondary_id is not None:
                await _reply_playlist(message, link.secondary_id, link.primary_id, cache, yandex)
            else:
                await _reply_playlist_uuid(message, link.primary_id, cache, yandex)
    except YMNotFound:
        await message.answer("😔 Не найдено или удалено из Яндекс.Музыки.")
    except YMUnauthorized:
        log.error("yandex token unauthorized — bot needs new token")
        await message.answer("⚠️ Сервис временно недоступен. Попробуй позже.")
    except YMTemporaryUnavailable:
        await message.answer("⚠️ Яндекс.Музыка временно ограничила запрос. Попробуй ещё раз чуть позже.")


async def _reply_track(
    message: Message,
    track_id: str,
    album_id: str | None,
    cache: Cache,
    yandex: YandexMusicClient,
    songlink: SongLinkClient,
) -> None:
    cached = await cache.get(f"track:{track_id}")
    if cached:
        track = cached["track"]
        links = cached.get("songlinks", {})
    else:
        track = await yandex.get_track(track_id)
        yandex_url = _canonical_track_url(track_id, album_id or track.get("album_id"))
        links = await songlink.get_links(yandex_url)
        await cache.set(f"track:{track_id}", {"track": track, "songlinks": links}, ttl_seconds=TTL_TRACK)

    caption = render_track(track, songlinks=links or None)
    photo = cover_url(track.get("cover_uri"))
    if photo:
        await message.answer_photo(photo, caption=caption, reply_markup=track_keyboard(track_id))
    else:
        await message.answer(caption, reply_markup=track_keyboard(track_id))


def _canonical_track_url(track_id: str, album_id: str | None) -> str:
    if album_id:
        return f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
    return f"https://music.yandex.ru/track/{track_id}"


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


async def _reply_playlist(
    message: Message,
    owner: str,
    kind: str,
    cache: Cache,
    yandex: YandexMusicClient,
) -> None:
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


async def _reply_playlist_uuid(
    message: Message,
    playlist_uuid: str,
    cache: Cache,
    yandex: YandexMusicClient,
) -> None:
    key = f"playlist_uuid:{playlist_uuid}"
    cached = await cache.get(key)
    playlist = cached or await _load_playlist_from_uuid_alias(cache, yandex, playlist_uuid)
    if not playlist:
        playlist = await yandex.get_playlist_by_uuid(playlist_uuid)

    if not cached:
        await _cache_uuid_playlist(cache, playlist_uuid, playlist)

    caption = render_playlist(playlist)
    photo = cover_url(playlist.get("cover_uri"))
    owner = playlist.get("owner", "")
    kind = playlist.get("id", "")
    if photo:
        await message.answer_photo(photo, caption=caption, reply_markup=playlist_open_keyboard(owner, kind))
    else:
        await message.answer(caption, reply_markup=playlist_open_keyboard(owner, kind))


async def _load_playlist_from_uuid_alias(
    cache: Cache,
    yandex: YandexMusicClient,
    playlist_uuid: str,
) -> dict | None:
    alias = await cache.get(f"playlist_uuid_alias:{playlist_uuid}")
    if not alias:
        return None

    owner = alias.get("owner", "")
    kind = alias.get("kind", "")
    if not owner or not kind:
        return None

    key = f"playlist:{owner}:{kind}"
    cached = await cache.get(key)
    if cached:
        return cached

    playlist = await yandex.get_playlist(owner, kind)
    await cache.set(key, playlist, ttl_seconds=TTL_PLAYLIST)
    return playlist


async def _cache_uuid_playlist(cache: Cache, playlist_uuid: str, playlist: dict) -> None:
    await cache.set(f"playlist_uuid:{playlist_uuid}", playlist, ttl_seconds=TTL_PLAYLIST)

    owner = playlist.get("owner", "")
    kind = playlist.get("id", "")
    if not owner or not kind:
        return

    await cache.set(f"playlist:{owner}:{kind}", playlist, ttl_seconds=TTL_PLAYLIST)
    await cache.set(
        f"playlist_uuid_alias:{playlist_uuid}",
        {"owner": owner, "kind": kind},
        ttl_seconds=TTL_PLAYLIST_UUID_ALIAS,
    )
