import asyncio
import json
import logging
import time
from typing import Any

import httpx
from yandex_music import Client as YMSyncClient
from yandex_music.exceptions import NotFoundError, UnauthorizedError

PLAYLIST_BY_UUID_API = "https://api.music.yandex.ru/playlist/{playlist_uuid}"
PLAYLIST_UUID_RETRY_DELAYS = (0.6,)
PLAYLIST_UUID_COOLDOWN_SECONDS = 180.0

log = logging.getLogger(__name__)


class YMError(Exception):
    pass


class YMNotFound(YMError):
    pass


class YMUnauthorized(YMError):
    pass


class YMTemporaryUnavailable(YMError):
    pass


class YMCaptchaChallenge(YMTemporaryUnavailable):
    pass


def _to_track_dict(track: Any) -> dict[str, Any]:
    album = track.albums[0] if track.albums else None
    return {
        "id": str(track.id),
        "title": track.title,
        "artists": [artist.name for artist in track.artists],
        "album_id": str(album.id) if album and getattr(album, "id", None) is not None else None,
        "album_title": album.title if album else "",
        "album_year": album.year if album else None,
        "duration_ms": track.duration_ms,
        "genre": album.genre if album else None,
        "cover_uri": track.cover_uri,
    }


def _to_album_dict(album: Any) -> dict[str, Any]:
    tracks = []
    if album.volumes:
        for volume in album.volumes:
            for track in volume:
                tracks.append({"title": track.title, "duration_ms": track.duration_ms})

    return {
        "id": str(album.id),
        "title": album.title,
        "artists": [artist.name for artist in album.artists],
        "year": album.year,
        "track_count": album.track_count or len(tracks),
        "duration_ms": sum(track["duration_ms"] for track in tracks),
        "cover_uri": album.cover_uri,
        "tracks": tracks,
    }


def _to_artist_dict(artist: Any, top_tracks: list[Any]) -> dict[str, Any]:
    cover_uri = None
    if artist.cover and artist.cover.items_uri:
        cover_uri = artist.cover.items_uri[0]

    return {
        "id": str(artist.id),
        "name": artist.name,
        "cover_uri": cover_uri,
        "top_tracks": [
            {"id": str(track.id), "title": track.title, "duration_ms": track.duration_ms}
            for track in top_tracks[:5]
        ],
    }


def _to_playlist_dict(playlist: Any) -> dict[str, Any]:
    tracks = []
    for short_track in playlist.tracks or []:
        track = short_track.track
        if not track:
            continue
        tracks.append(
            {
                "title": track.title,
                "artists": [artist.name for artist in track.artists],
                "duration_ms": track.duration_ms,
            }
        )

    return {
        "id": str(playlist.kind),
        "owner": playlist.owner.login if playlist.owner else "",
        "title": playlist.title,
        "track_count": playlist.track_count or len(tracks),
        "duration_ms": sum(track["duration_ms"] for track in tracks),
        "cover_uri": playlist.cover.uri if playlist.cover else None,
        "tracks": tracks,
    }


def _to_uuid_playlist_dict(payload: dict[str, Any]) -> dict[str, Any]:
    tracks = []
    for item in payload.get("tracks", []):
        track = item.get("track") or {}
        artists = [artist.get("name") for artist in track.get("artists", []) if artist.get("name")]
        tracks.append(
            {
                "title": track.get("title", ""),
                "artists": artists,
                "duration_ms": track.get("durationMs") or 0,
            }
        )

    owner = payload.get("owner") or {}
    return {
        "id": str(payload.get("kind", "")),
        "owner": owner.get("login", ""),
        "title": payload.get("title", ""),
        "track_count": payload.get("trackCount") or len(tracks),
        "duration_ms": payload.get("durationMs") or sum(track["duration_ms"] for track in tracks),
        "cover_uri": (payload.get("cover") or {}).get("uri"),
        "tracks": tracks,
        "playlist_uuid": payload.get("playlistUuid"),
    }


class YandexMusicClient:
    def __init__(self, token: str):
        self._sync = YMSyncClient(token).init()
        self._playlist_uuid_blocked_until = 0.0
        self._playlist_uuid_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}

    async def _run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except UnauthorizedError as exc:
            raise YMUnauthorized(str(exc)) from exc
        except NotFoundError as exc:
            raise YMNotFound(str(exc)) from exc

    async def get_track(self, track_id: str) -> dict[str, Any]:
        tracks = await self._run(self._sync.tracks, [track_id])
        if not tracks:
            raise YMNotFound(f"track {track_id} not found")
        return _to_track_dict(tracks[0])

    async def get_album(self, album_id: str) -> dict[str, Any]:
        album = await self._run(self._sync.albums_with_tracks, album_id)
        if not album:
            raise YMNotFound(f"album {album_id} not found")
        return _to_album_dict(album)

    async def get_artist(self, artist_id: str) -> dict[str, Any]:
        brief = await self._run(self._sync.artists_brief_info, artist_id)
        if not brief or not brief.artist:
            raise YMNotFound(f"artist {artist_id} not found")
        return _to_artist_dict(brief.artist, brief.popular_tracks or [])

    async def get_playlist(self, owner: str, kind: str) -> dict[str, Any]:
        playlist = await self._run(self._sync.users_playlists, kind, owner)
        if not playlist:
            raise YMNotFound(f"playlist {owner}/{kind} not found")
        return _to_playlist_dict(playlist)

    async def get_playlist_by_uuid(self, playlist_uuid: str) -> dict[str, Any]:
        existing_task = self._playlist_uuid_tasks.get(playlist_uuid)
        if existing_task is not None:
            return await asyncio.shield(existing_task)

        now = time.monotonic()
        if now < self._playlist_uuid_blocked_until:
            raise YMTemporaryUnavailable("playlist uuid lookup cooldown is active")

        task = asyncio.create_task(self._fetch_playlist_by_uuid(playlist_uuid))
        self._playlist_uuid_tasks[playlist_uuid] = task
        try:
            return await asyncio.shield(task)
        finally:
            if self._playlist_uuid_tasks.get(playlist_uuid) is task:
                self._playlist_uuid_tasks.pop(playlist_uuid, None)

    async def _fetch_playlist_by_uuid(self, playlist_uuid: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(len(PLAYLIST_UUID_RETRY_DELAYS) + 1):
            try:
                response = await asyncio.to_thread(
                    httpx.get,
                    PLAYLIST_BY_UUID_API.format(playlist_uuid=playlist_uuid),
                    headers={"Authorization": f"OAuth {self._sync.token}"},
                    params={"richTracks": "true"},
                    follow_redirects=True,
                    timeout=20.0,
                )
                return self._parse_playlist_uuid_response(playlist_uuid, response)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= len(PLAYLIST_UUID_RETRY_DELAYS):
                    break
                await asyncio.sleep(PLAYLIST_UUID_RETRY_DELAYS[attempt])
            except YMUnauthorized:
                raise
            except YMNotFound:
                raise
            except YMCaptchaChallenge as exc:
                self._playlist_uuid_blocked_until = time.monotonic() + PLAYLIST_UUID_COOLDOWN_SECONDS
                log.warning("playlist uuid endpoint hit captcha, enabling cooldown for %.0fs", PLAYLIST_UUID_COOLDOWN_SECONDS)
                raise YMTemporaryUnavailable("playlist uuid lookup blocked by captcha") from exc
            except YMTemporaryUnavailable as exc:
                last_error = exc
                if attempt >= len(PLAYLIST_UUID_RETRY_DELAYS):
                    break
                await asyncio.sleep(PLAYLIST_UUID_RETRY_DELAYS[attempt])

        raise YMTemporaryUnavailable("playlist uuid lookup failed after retries") from last_error

    def _parse_playlist_uuid_response(self, playlist_uuid: str, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 401:
            raise YMUnauthorized("unauthorized")
        if response.status_code == 404:
            raise YMNotFound(f"playlist {playlist_uuid} not found")
        if "showcaptcha" in str(response.url):
            raise YMCaptchaChallenge("playlist uuid lookup blocked by captcha")

        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            raise YMCaptchaChallenge("playlist uuid lookup returned non-json response")

        try:
            data = response.json().get("result")
        except json.JSONDecodeError as exc:
            raise YMTemporaryUnavailable("playlist uuid lookup returned invalid json") from exc

        if not data:
            raise YMNotFound(f"playlist {playlist_uuid} not found")
        return _to_uuid_playlist_dict(data)

    async def get_similar(self, track_id: str) -> list[dict[str, Any]]:
        similar = await self._run(self._sync.tracks_similar, track_id)
        if not similar or not similar.similar_tracks:
            return []
        return [
            {
                "id": str(track.id),
                "title": track.title,
                "artists": [artist.name for artist in track.artists],
                "duration_ms": track.duration_ms,
            }
            for track in similar.similar_tracks[:5]
        ]
