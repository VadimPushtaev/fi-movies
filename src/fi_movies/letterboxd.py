from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


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


def parse_film_genres(html_text: str) -> tuple[str, ...]:
    """Read genre names from a Letterboxd film's Genres tab."""
    soup = BeautifulSoup(html_text, "html.parser")
    links = soup.select('#tab-panel-genres a[href^="/films/genre/"]')
    return tuple(dict.fromkeys(link.get_text(" ", strip=True) for link in links if link.get_text(strip=True)))


async def fetch_film_genres(
    film_urls: Iterable[str | None],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, tuple[str, ...] | None]:
    """Fetch each exact Letterboxd film once; None means that a request failed."""
    urls = {url for url in film_urls if url and rating_embed_url(url)}
    semaphore = asyncio.Semaphore(3)

    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": "FI Movies timetable importer"},
        transport=transport,
    ) as client:
        async def fetch(url: str) -> tuple[str, tuple[str, ...] | None]:
            async with semaphore:
                try:
                    response = await client.get(film_page_url(url) or url)
                    response.raise_for_status()
                    return url, parse_film_genres(response.text)
                except httpx.HTTPError as exc:
                    logger.warning("Could not fetch Letterboxd genres for %s: %s", url, exc)
                    return url, None

        return dict(await asyncio.gather(*(fetch(url) for url in sorted(urls))))
