import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

PLATFORMS = {
    "spotify": "Spotify",
    "appleMusic": "Apple Music",
    "youtubeMusic": "YouTube Music",
    "deezer": "Deezer",
    "tidal": "TIDAL",
    "amazonMusic": "Amazon Music",
}

API_URL = "https://api.song.link/v1-alpha.1/links"
RETRY_DELAYS = (0.4,)


class SongLinkClient:
    def __init__(self, timeout: float = 2.0):
        self._client = httpx.AsyncClient(timeout=timeout)

    async def get_links(self, yandex_url: str) -> dict[str, str]:
        response = await self._request_links(yandex_url)
        if response is None:
            return {}

        if response.status_code != 200:
            log.warning("songlink non-200 for %s: %s", yandex_url, response.status_code)
            return {}

        try:
            data = response.json()
            links = data["linksByPlatform"]
        except (KeyError, ValueError):
            return {}

        resolved = {
            label: links[key]["url"]
            for key, label in PLATFORMS.items()
            if key in links and "url" in links[key]
        }
        if not resolved:
            log.info("songlink returned no supported platforms for %s", yandex_url)
        return resolved

    async def _request_links(self, yandex_url: str) -> httpx.Response | None:
        last_error: httpx.HTTPError | None = None
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                return await self._client.get(API_URL, params={"url": yandex_url, "userCountry": "RU"})
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= len(RETRY_DELAYS):
                    break
                await asyncio.sleep(RETRY_DELAYS[attempt])

        if last_error is not None:
            log.warning(
                "songlink request failed for %s: %s: %s",
                yandex_url,
                type(last_error).__name__,
                last_error,
            )
        return None

    async def close(self) -> None:
        await self._client.aclose()
