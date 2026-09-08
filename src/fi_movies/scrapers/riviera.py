from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, time
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from fi_movies.scrapers.nytleffaan import (
    NormalizedMovie,
    NormalizedPayload,
    NormalizedShowtime,
    NormalizedTheater,
    clean_text,
    parse_int,
    slugify,
)

SOURCE = "riviera"
ALL_THEATERS_AREA_ID = "1040"


class RivieraScraper:
    def __init__(self, *, base_url: str = "https://www.rivieracinemas.fi", timeout_seconds: float = 30.0) -> None:
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
            page = await client.get(f"{self.base_url}/elokuvat/")
            page.raise_for_status()
            dates = listing_dates(page.text)
            payloads = []
            for item in dates:
                response = await client.post(
                    f"{self.base_url}/wp/wp-admin/admin-ajax.php",
                    data={
                        "action": "filter_movies",
                        "date": item.strftime("%d.%m.%Y"),
                        "movie": "",
                        "area": ALL_THEATERS_AREA_ID,
                        "initial": "true",
                    },
                )
                response.raise_for_status()
                data = response.json()
                movies_html = data.get("data", {}).get("movies", "") if isinstance(data, dict) else ""
                payloads.append(normalize_listing_html(str(movies_html), base_url=self.base_url))
            return merge_payloads(payloads)


def listing_dates(html_text: str) -> list[date]:
    soup = BeautifulSoup(html_text, "html.parser")
    dates = []
    for option in soup.select(".select-date option[value]"):
        parsed = parse_date(str(option.get("value") or ""))
        if parsed is not None:
            dates.append(parsed)
    return list(dict.fromkeys(dates))


def normalize_listing_html(html_text: str, *, base_url: str) -> NormalizedPayload:
    soup = BeautifulSoup(html_text, "html.parser")
    movies: dict[str, NormalizedMovie] = {}
    theaters: dict[str, NormalizedTheater] = {}
    showtimes: dict[str, NormalizedShowtime] = {}
    for row in soup.select(".movielist__item"):
        movie = normalize_movie_row(row, base_url=base_url)
        theater = normalize_theater_row(row)
        showtime = normalize_showtime_row(row, movie=movie, theater=theater, base_url=base_url)
        if movie is None or theater is None or showtime is None:
            continue
        movies[movie.source_movie_id] = movie
        theaters[theater.source_theater_id] = theater
        showtimes[showtime.source_key] = showtime

    return NormalizedPayload(
        movies=sorted(movies.values(), key=lambda movie: movie.source_movie_id),
        theaters=sorted(theaters.values(), key=lambda theater: theater.source_theater_id),
        showtimes=sorted(showtimes.values(), key=lambda showtime: showtime.source_key),
    )


def normalize_movie_row(row: Any, *, base_url: str) -> NormalizedMovie | None:
    link = row.select_one(".movielist__item__title[href]")
    title = text_or_none(link)
    source_movie_id = movie_id_from_url(str(link.get("href") or "")) if link else None
    if not title or not source_movie_id:
        return None
    return NormalizedMovie(
        source=SOURCE,
        source_movie_id=source_movie_id,
        source_internal_id=None,
        slug=slugify(title),
        title=title,
        original_title=None,
        swedish_title=None,
        poster_url=None,
        trailer_url=None,
        age_limit=None,
        duration_minutes=duration_minutes_from_row(row),
        genres=[],
        distributor=None,
        premiere_date=None,
        description=None,
        director=None,
        script=None,
        actors=None,
        raw_url=urljoin(base_url, str(link.get("href") or "")),
    )


def normalize_theater_row(row: Any) -> NormalizedTheater | None:
    location = text_or_none(row.select_one(".location"))
    if not location:
        return None
    theater_name, _auditorium = parse_location(location)
    source_theater_id = slugify(f"riviera-{theater_name}")
    return NormalizedTheater(
        source=SOURCE,
        source_theater_id=source_theater_id,
        city_slug="helsinki",
        city_name="Helsinki",
        name="Riviera",
        address=riviera_address(theater_name),
        webpage_url=riviera_webpage(theater_name),
        phone_number=None,
        email="info@rivieracinemas.fi",
        latitude=None,
        longitude=None,
        api_id=None,
    )


def normalize_showtime_row(
    row: Any,
    *,
    movie: NormalizedMovie | None,
    theater: NormalizedTheater | None,
    base_url: str,
) -> NormalizedShowtime | None:
    if movie is None or theater is None:
        return None
    starts_at = starts_at_from_row(row)
    if starts_at is None:
        return None
    ticket_link = row.select_one(".movielist__item__actions a[href]")
    order_page_url = urljoin(base_url, str(ticket_link.get("href") or "")) if ticket_link else None
    source_show_id = show_id_from_url(order_page_url)
    _theater_name, auditorium = parse_location(text_or_none(row.select_one(".location")) or "")
    key_parts = [
        SOURCE,
        source_show_id or "",
        theater.source_theater_id,
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
        source_theater_id=theater.source_theater_id,
        auditorium=auditorium,
        starts_at=starts_at,
        ends_at=None,
        order_page_url=order_page_url,
    )


def merge_payloads(payloads: list[NormalizedPayload]) -> NormalizedPayload:
    movies: dict[tuple[str, str], NormalizedMovie] = {}
    theaters: dict[tuple[str, str], NormalizedTheater] = {}
    showtimes: dict[str, NormalizedShowtime] = {}
    for payload in payloads:
        for movie in payload.movies:
            movies[(movie.source, movie.source_movie_id)] = movie
        for theater in payload.theaters:
            theaters[(theater.source, theater.source_theater_id)] = theater
        for showtime in payload.showtimes:
            showtimes[showtime.source_key] = showtime
    return NormalizedPayload(
        movies=sorted(movies.values(), key=lambda movie: (movie.source, movie.source_movie_id)),
        theaters=sorted(theaters.values(), key=lambda theater: (theater.source, theater.source_theater_id)),
        showtimes=sorted(showtimes.values(), key=lambda showtime: showtime.source_key),
    )


def starts_at_from_row(row: Any) -> datetime | None:
    parsed_date = parse_date(text_or_none(row.select_one(".date")) or "")
    parsed_time = parse_time(text_or_none(row.select_one(".time")) or "")
    if parsed_date is None or parsed_time is None:
        return None
    return datetime.combine(parsed_date, parsed_time)


def parse_date(value: str) -> date | None:
    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", value)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    return date(year, month, day)


def parse_time(value: str) -> time | None:
    match = re.search(r"(\d{1,2})[:.](\d{2})", value)
    if not match:
        return None
    hour, minute = (int(part) for part in match.groups())
    return time(hour, minute)


def parse_location(value: str) -> tuple[str, str | None]:
    parts = [part.strip() for part in value.split(",", maxsplit=1)]
    theater = parts[0] if parts and parts[0] else "Riviera"
    auditorium = parts[1] if len(parts) > 1 and parts[1] else None
    return theater, auditorium


def movie_id_from_url(url: str) -> str | None:
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0].lower() == "event":
        return parts[1]
    return None


def show_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    return (parse_qs(urlparse(url).query).get("show") or [None])[0]


def duration_minutes_from_row(row: Any) -> int | None:
    raw = text_or_none(row.select_one(".length"))
    if not raw:
        return None
    hours = parse_int((re.search(r"(\d+)\s*h", raw) or [None, "0"])[1]) or 0
    minutes = parse_int((re.search(r"(\d+)\s*min", raw) or [None, "0"])[1]) or 0
    total = hours * 60 + minutes
    return total or None


def riviera_address(theater_name: str) -> str | None:
    if theater_name.lower() == "kallio":
        return "Harjukatu 2, 00500 Helsinki"
    if theater_name.lower() == "punavuori":
        return "Telakkakatu 7, 00150 Helsinki"
    return None


def riviera_webpage(theater_name: str) -> str:
    if theater_name.lower() == "kallio":
        return "https://www.rivieracinemas.fi/elokuvateatteri-kallio/"
    if theater_name.lower() == "punavuori":
        return "https://www.rivieracinemas.fi/elokuvateatteri-punavuori/"
    return "https://www.rivieracinemas.fi/"


def text_or_none(element: Any) -> str | None:
    return clean_text(element.get_text(" ", strip=True)) if element else None
