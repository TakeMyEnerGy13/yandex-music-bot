from bot.renderers._helpers import format_duration, html_escape

MAX_TRACKS = 10


def render_playlist(playlist: dict) -> str:
    title = html_escape(playlist["title"])
    owner = html_escape(playlist["owner"])
    track_count = playlist["track_count"]
    duration = format_duration(playlist["duration_ms"])

    header = [
        f"📃 <b>{title}</b>",
        f"by {owner} · {track_count} tracks · {duration}",
        "",
    ]

    tracks = playlist["tracks"][:MAX_TRACKS]
    body = [
        f"{index}. {html_escape(track['title'])} — {html_escape(', '.join(track['artists']))} · {format_duration(track['duration_ms'])}"
        for index, track in enumerate(tracks, start=1)
    ]

    if track_count > MAX_TRACKS:
        body.append(f"… and {track_count - MAX_TRACKS} more")

    return "\n".join(header + body)
