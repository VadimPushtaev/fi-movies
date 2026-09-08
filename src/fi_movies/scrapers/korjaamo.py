from __future__ import annotations

import hashlib
import re
from datetime import datetime
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
    slugify,
)

SOURCE = "korjaamo"
THEATER_ID = "korjaamo-kino"


class KorjaamoKinoScraper:
    def __init__(self, *, base_url: str = "https://korjaamokino.fi", timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def scrape(self) -> NormalizedPayload:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
            response = await client.get(f"{self.base_url}/schedule")
            response.raise_for_status()
            return normalize_schedule_html(response.text, base_url=self.base_url)


def normalize_schedule_html(html_text: str, *, base_url: str) -> NormalizedPayload:
    soup = BeautifulSoup(html_text, "html.parser")
    movies: dict[str, NormalizedMovie] = {}
    showtimes: dict[str, NormalizedShowtime] = {}
    for card in soup.select(".schedule-card"):
        movie = normalize_movie_card(card, base_url=base_url)
        showtime = normalize_showtime_card(card, movie=movie)
        if movie is None or showtime is None:
            continue
        movies[movie.source_movie_id] = movie
        showtimes[showtime.source_key] = showtime

    return NormalizedPayload(
        movies=sorted(movies.values(), key=lambda movie: movie.source_movie_id),
        theaters=[korjaamo_theater()],
        showtimes=sorted(showtimes.values(), key=lambda showtime: showtime.source_key),
    )


def normalize_movie_card(card: Any, *, base_url: str) -> NormalizedMovie | None:
    link = card.select_one(".schedule-card__title-container a[href]")
    title = text_or_none(card.select_one(".schedule-card__title"))
    source_movie_id = event_id_from_url(str(link["href"])) if link else None
    if not title or not source_movie_id:
        return None

    original_title = text_or_none(card.select_one(".schedule-card__secondary-title"))
    return NormalizedMovie(
        source=SOURCE,
        source_movie_id=source_movie_id,
        source_internal_id=None,
        slug=slugify(original_title or title),
        title=title,
        original_title=original_title,
        swedish_title=None,
        poster_url=poster_url_from_card(card, base_url=base_url),
        trailer_url=trailer_url_from_card(card, base_url=base_url),
        age_limit=age_limit_from_card(card),
        duration_minutes=None,
        genres=genres_from_card(card),
        distributor=None,
        premiere_date=None,
        description=None,
        director=None,
        script=None,
        actors=None,
        raw_url=urljoin(base_url, str(link["href"])),
    )


def normalize_showtime_card(card: Any, *, movie: NormalizedMovie | None) -> NormalizedShowtime | None:
    if movie is None:
        return None
    starts_at = datetime_from_card(card)
    if starts_at is None:
        return None
    order_link = card.select_one("a.schedule-card__primary-button[href]")
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
        auditorium="Sali",
        starts_at=starts_at,
        ends_at=None,
        order_page_url=order_page_url,
    )


def korjaamo_theater() -> NormalizedTheater:
    return NormalizedTheater(
        source=SOURCE,
        source_theater_id=THEATER_ID,
        city_slug="helsinki",
        city_name="Helsinki",
        name="Korjaamo Kino",
        address="Töölönkatu 51 B, 00250 Helsinki",
        webpage_url="https://korjaamokino.fi/",
        phone_number=None,
        email="info@korjaamo.fi",
        latitude=None,
        longitude=None,
        api_id=None,
    )


def event_id_from_url(url: str) -> str | None:
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "event":
        return parts[1]
    return None


def show_id_from_order_url(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"/show/([^/?#]+)", url)
    return match.group(1) if match else None


def datetime_from_card(card: Any) -> datetime | None:
    time_element = card.select_one(".schedule-card__time[datetime]")
    if time_element is None:
        return None
    raw = str(time_element.get("datetime") or "")
    raw = re.sub(r"(\.\d{6})\d+", r"\1", raw)
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def age_limit_from_card(card: Any) -> str | None:
    raw = text_or_none(card.select_one(".schedule-card__tag"))
    if raw is None:
        return None
    return raw.removeprefix("K-")


def genres_from_card(card: Any) -> list[str]:
    genres = []
    for item in card.select(".schedule-card__genre"):
        text = clean_text(item.get_text(" ", strip=True))
        if text:
            genres.append(text.strip(", "))
    return [genre for genre in genres if genre]


def poster_url_from_card(card: Any, *, base_url: str) -> str | None:
    image = card.select_one(".schedule-card__image img")
    if image is None:
        return None
    return first_srcset_url(str(image.get("data-srcset") or ""), base_url=base_url)


def trailer_url_from_card(card: Any, *, base_url: str) -> str | None:
    button = card.select_one(".js-event-trailer-button[data-src]")
    if button is None:
        return None
    raw = clean_text(button.get("data-src"))
    return urljoin(base_url, raw) if raw else None


def first_srcset_url(srcset: str, *, base_url: str) -> str | None:
    first = srcset.split(",", maxsplit=1)[0].strip()
    if not first:
        return None
    url = first.split(" ", maxsplit=1)[0]
    if url.startswith("//"):
        return f"https:{url}"
    return urljoin(base_url, url)


def text_or_none(element: Any) -> str | None:
    return clean_text(element.get_text(" ", strip=True)) if element else None
