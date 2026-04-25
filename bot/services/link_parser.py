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
    (re.compile(r"^/album/(\d+)/track/(\d+)$"), "track", True),
    (re.compile(r"^/track/(\d+)$"), "track", False),
    (re.compile(r"^/album/(\d+)$"), "album", False),
    (re.compile(r"^/users/([^/]+)/playlists/(\d+)$"), "playlist", True),
    (re.compile(r"^/playlists/([0-9a-fA-F-]{36})$"), "playlist", False),
    (re.compile(r"^/artist/(\d+)$"), "artist", False),
]


@dataclass(frozen=True)
class ParsedLink:
    type: LinkType
    primary_id: str
    secondary_id: str | None = None


def parse(url: object) -> ParsedLink | None:
    if not isinstance(url, str):
        return None

    parsed = urlparse(url.strip())
    if parsed.netloc not in ALLOWED_HOSTS:
        return None

    path = parsed.path.rstrip("/")
    if not path:
        return None

    for pattern, link_type, has_secondary in _PATTERNS:
        match = pattern.fullmatch(path)
        if not match:
            continue

        if link_type == "track" and has_secondary:
            return ParsedLink(type="track", primary_id=match.group(2), secondary_id=match.group(1))

        if link_type == "playlist" and has_secondary:
            return ParsedLink(type="playlist", primary_id=match.group(2), secondary_id=match.group(1))

        return ParsedLink(type=link_type, primary_id=match.group(1))

    return None
