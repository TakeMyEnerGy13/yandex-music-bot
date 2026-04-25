from bot.renderers._helpers import format_duration, html_escape


def render_track(track: dict, songlinks: dict[str, str] | None = None) -> str:
    title = html_escape(track["title"])
    artists = html_escape(", ".join(track["artists"]))
    album = html_escape(track["album_title"])
    year = track.get("album_year") or "—"
    duration = format_duration(track["duration_ms"])
    genre = track.get("genre")

    duration_line = f"⏱ {duration}"
    if genre:
        duration_line += f" · 🎼 {html_escape(genre)}"

    lines = [
        f"🎵 <b>{title}</b>",
        f"👤 {artists}",
        f"💿 {album} ({year})",
        duration_line,
    ]

    if songlinks:
        platform_links = " · ".join(
            f'<a href="{html_escape(url, quote=True)}">{html_escape(name)}</a>'
            for name, url in songlinks.items()
        )
        lines.extend(["", f"🔗 Other platforms: {platform_links}"])

    return "\n".join(lines)
