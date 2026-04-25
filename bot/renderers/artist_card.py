from bot.renderers._helpers import format_duration, html_escape


def render_artist(artist: dict) -> str:
    name = html_escape(artist["name"])
    lines = [f"👤 <b>{name}</b>", "", "Top tracks:"]

    for index, track in enumerate(artist.get("top_tracks", [])[:5], start=1):
        lines.append(f"{index}. {html_escape(track['title'])} — {format_duration(track['duration_ms'])}")

    return "\n".join(lines)
