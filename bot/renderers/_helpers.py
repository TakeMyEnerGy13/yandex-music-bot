from html import escape as _escape


def format_duration(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def cover_url(uri_template: str | None, size: str = "400x400") -> str | None:
    if not uri_template:
        return None
    return f"https://{uri_template.replace('%%', size)}"


def html_escape(text: object, *, quote: bool = False) -> str:
    return _escape(str(text), quote=quote)
