from __future__ import annotations

import re
from urllib.parse import urlparse


def film_page_url(url: str | None) -> str | None:
    """Point known Letterboxd film subpages at the main film page."""
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in {"letterboxd.com", "www.letterboxd.com"}:
        return url
    if parsed.query or parsed.fragment:
        return url
    match = re.fullmatch(r"/film/([a-z0-9-]+)/cast/?", parsed.path)
    if match:
        return f"https://letterboxd.com/film/{match.group(1)}/"
    return url


def rating_embed_url(film_url: str | None) -> str | None:
    """Return Letterboxd's official ratings embed for an exact film link."""
    film_url = film_page_url(film_url)
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
