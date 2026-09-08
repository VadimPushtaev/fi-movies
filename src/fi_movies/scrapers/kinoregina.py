from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from fi_movies.scrapers.nytleffaan import (
    NormalizedMovie,
    NormalizedPayload,
    NormalizedShowtime,
    NormalizedTheater,
    clean_text,
    parse_datetime,
    slugify,
)

SOURCE = "kinoregina"
THEATER_ID = "kino-regina"


@dataclass(frozen=True)
class KinoReginaEndpoints:
    showtimes_url: str


class KinoReginaScraper:
    def __init__(self, *, base_url: str = "https://kinoregina.fi", timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def scrape(self, *, start_date: date) -> NormalizedPayload:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
            response = await client.post(
                self.showtimes_url,
                data={"getShowtimesMovies": start_date.isoformat()},
            )
            response.raise_for_status()
            return normalize_showtime_html(response.text, base_url=self.base_url)

    @property
    def showtimes_url(self) -> str:
        return urljoin(
            self.base_url,
            "/wp-content/themes/kinoregina2/assets/functions/getShowtimesMoviesV2.php",
        )


def normalize_showtime_html(html_text: str, *, base_url: str) -> NormalizedPayload:
    soup = BeautifulSoup(html_text, "html.parser")
    movies: dict[str, NormalizedMovie] = {}
    showtimes: dict[str, NormalizedShowtime] = {}
    for card in soup.select(".movie"):
        movie = normalize_movie_card(card, base_url=base_url)
        showtime = normalize_showtime_card(card, movie=movie)
        if movie is None or showtime is None:
            continue
        movies[movie.source_movie_id] = movie
        showtimes[showtime.source_key] = showtime

    return NormalizedPayload(
        movies=sorted(movies.values(), key=lambda movie: movie.source_movie_id),
        theaters=[kinoregina_theater()],
        showtimes=sorted(showtimes.values(), key=lambda showtime: showtime.source_key),
    )


def normalize_movie_card(card: Any, *, base_url: str) -> NormalizedMovie | None:
    link = card.select_one("a.title[href]")
    title = clean_text(link.get_text(" ", strip=True)) if link else None
    source_movie_id = movie_id_from_url(str(link["href"])) if link else None
    if not title or not source_movie_id:
        return None

    return NormalizedMovie(
        source=SOURCE,
        source_movie_id=source_movie_id,
        source_internal_id=None,
        slug=slugify(title),
        title=title,
        original_title=original_title_from_title(title),
        swedish_title=None,
        poster_url=poster_url_from_card(card, base_url=base_url),
        trailer_url=None,
        age_limit=None,
        duration_minutes=None,
        genres=[],
        distributor=None,
        premiere_date=None,
        description=clean_text(text_or_none(card.select_one(".movie-content p"))),
        director=None,
        script=None,
        actors=None,
        raw_url=urljoin(base_url, str(link["href"])),
    )


def normalize_showtime_card(card: Any, *, movie: NormalizedMovie | None) -> NormalizedShowtime | None:
    if movie is None:
        return None
    start_text = text_or_none(card.select_one(".calendar-icon .start"))
    starts_at = parse_datetime(start_text)
    if starts_at is None:
        return None
    order_link = card.select_one("a.add-to-cart[href]")
    order_page_url = clean_text(order_link.get("href")) if order_link else None
    source_show_id = show_id_from_order_url(order_page_url)
    key_parts = [
        SOURCE,
        source_show_id or "",
        THEATER_ID,
        movie.source_movie_id,
        starts_at.isoformat(timespec="minutes"),
        order_page_url or "",
    ]
    source_key = hashlib.sha256("|".join(key_parts).encode("utf-8")).hexdigest()
    return NormalizedShowtime(
        source=SOURCE,
        source_key=source_key,
        source_show_id=source_show_id,
        source_raw_id=None,
        source_movie_id=movie.source_movie_id,
        source_theater_id=THEATER_ID,
        auditorium=None,
        starts_at=starts_at,
        ends_at=None,
        order_page_url=order_page_url,
    )


def kinoregina_theater() -> NormalizedTheater:
    return NormalizedTheater(
        source=SOURCE,
        source_theater_id=THEATER_ID,
        city_slug="helsinki",
        city_name="Helsinki",
        name="Kino Regina",
        address="Töölönlahdenkatu 4, 00100 Helsinki",
        webpage_url="https://kinoregina.fi/",
        phone_number="040 4553 380",
        email="kinoregina@kavi.fi",
        latitude=60.1745,
        longitude=24.9384,
        api_id=None,
    )


def movie_id_from_url(url: str) -> str | None:
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[-2] == "elokuva":
        return parts[-1]
    return None


def show_id_from_order_url(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"/show/([^/?#]+)", url)
    return match.group(1) if match else None


def poster_url_from_card(card: Any, *, base_url: str) -> str | None:
    poster = card.select_one(".img-container")
    if poster is None:
        return None
    style = str(poster.get("style") or "")
    match = re.search(r"background-image:\s*url\(['\"]?([^'\")]+)", style)
    if not match:
        return None
    return urljoin(base_url, match.group(1))


def original_title_from_title(title: str) -> str:
    parts = re.split(r"\s+[–-]\s+", title, maxsplit=1)
    return parts[0].strip()


def text_or_none(element: Any) -> str | None:
    return element.get_text(" ", strip=True) if element else None
