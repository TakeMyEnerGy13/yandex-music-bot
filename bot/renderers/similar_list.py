from bot.renderers._helpers import format_duration, html_escape


def render_similar(source_title: str, tracks: list[dict]) -> str:
    lines = [f"🎯 Похожие на «{html_escape(source_title)}»:", ""]

    for index, track in enumerate(tracks, start=1):
        link = f"https://music.yandex.ru/track/{track['id']}"
        artists = html_escape(", ".join(track["artists"]))
        lines.append(
            f'{index}. <a href="{link}">{html_escape(track["title"])}</a> — {artists} · {format_duration(track["duration_ms"])}'
        )

    return "\n".join(lines)
