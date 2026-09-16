from __future__ import annotations

import re
from urllib.parse import urlparse


def rating_embed_url(film_url: str | None) -> str | None:
    """Return Letterboxd's official ratings embed for an exact film link."""
    if not film_url:
        return None
    parsed = urlparse(film_url)
    if parsed.scheme != "https" or parsed.netloc not in {"letterboxd.com", "www.letterboxd.com"}:
        return None
    if parsed.query or parsed.fragment:
        return None
    path = parsed.path.strip("/")
    if not re.fullmatch(r"(?:film/[a-z0-9-]+|tmdb/[0-9]+|imdb/tt[0-9]+)", path):
        return None
    return f"https://embed.letterboxd.com/{path}/embed-histogram/?notitle=true&theme=light"
