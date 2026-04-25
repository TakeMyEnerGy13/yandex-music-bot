from bot.renderers._helpers import format_duration, html_escape

MAX_TRACKS = 15


def render_album(album: dict) -> str:
    title = html_escape(album["title"])
    artists = html_escape(", ".join(album["artists"]))
    year = album.get("year") or "—"
    track_count = album["track_count"]
    duration = format_duration(album["duration_ms"])

    header = [
        f"💿 <b>{title}</b>",
        f"👤 {artists} · {year} · {track_count} tracks · {duration}",
        "",
    ]

    tracks = album["tracks"][:MAX_TRACKS]
    body = [
        f"{index}. {html_escape(track['title'])} — {format_duration(track['duration_ms'])}"
        for index, track in enumerate(tracks, start=1)
    ]

    if track_count > MAX_TRACKS:
        body.append(f"… and {track_count - MAX_TRACKS} more")

    return "\n".join(header + body)
