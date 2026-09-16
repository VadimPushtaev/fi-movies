from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from fi_movies.letterboxd import film_page_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HiffMovieData:
    source_url: str
    title: str
    original_title: str | None
    poster_url: str | None
    letterboxd_url: str
    release_year: int | None


@dataclass(frozen=True)
class HiffScreeningData:
    source_key: str
    movie_url: str
    venue: str
    starts_at: datetime
    ends_at: datetime | None
    duration_minutes: int | None
    screening_number: int | None
    screening_total: int | None


@dataclass(frozen=True)
class HiffPayload:
    movies: list[HiffMovieData]
    screenings: list[HiffScreeningData]


@dataclass(frozen=True)
class HiffMoviePage:
    original_title: str | None
    poster_url: str | None
    letterboxd_url: str | None
    release_year: int | None


class HiffScraper:
    def __init__(
        self,
        *,
        timetable_url: str = "https://hiff.fi/en/love-anarchy/timetable/",
        timeout_seconds: float = 30.0,
        max_concurrency: int = 8,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timetable_url = timetable_url
        self.timeout_seconds = timeout_seconds
        self.max_concurrency = max_concurrency
        self.transport = transport

    async def scrape(self) -> HiffPayload:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "FI Movies timetable importer"},
            transport=self.transport,
        ) as client:
            response = await client.get(self.timetable_url)
            response.raise_for_status()
            titles, screenings = parse_timetable_html(response.text, base_url=self.timetable_url)
            if not screenings:
                raise ValueError("HIFF timetable contained no screenings")

            semaphore = asyncio.Semaphore(self.max_concurrency)

            async def fetch_movie(url: str, title: str) -> HiffMovieData:
                details = HiffMoviePage(None, None, None, None)
                try:
                    async with semaphore:
                        film_response = await client.get(url)
                        film_response.raise_for_status()
                    details = parse_movie_html(film_response.text, base_url=url)
                except (httpx.HTTPError, ValueError):
                    logger.exception("Could not load HIFF film details from %s", url)
                search_title = details.original_title or title
                return HiffMovieData(
                    source_url=url,
                    title=title,
                    original_title=details.original_title,
                    poster_url=details.poster_url,
                    letterboxd_url=details.letterboxd_url or letterboxd_search_url(search_title),
                    release_year=details.release_year,
                )

            movies = await asyncio.gather(*(fetch_movie(url, title) for url, title in titles.items()))
            return HiffPayload(movies=movies, screenings=screenings)


def parse_timetable_html(html_text: str, *, base_url: str) -> tuple[dict[str, str], list[HiffScreeningData]]:
    soup = BeautifulSoup(html_text, "html.parser")
    titles: dict[str, str] = {}
    screenings: list[HiffScreeningData] = []
    for item in soup.select("li.event.item"):
        link = item.select_one("a[href]")
        title = clean_text(item.get("data-title"))
        venue = clean_text(item.get("data-venue"))
        starts_at = parse_datetime(item.get("data-time"))
        if link is None or not title or not venue or starts_at is None:
            continue

        movie_url = urljoin(base_url, str(link.get("href")))
        titles.setdefault(movie_url, title)
        duration_text = element_text(item.select_one(".duration"))
        start_text = element_text(item.select_one(".start-time"))
        duration, number, total = parse_duration_and_sequence(duration_text)
        show_id = None
        indicator = item.select_one("[data-show-rec-id]")
        if indicator is not None:
            show_id = clean_text(indicator.get("data-show-rec-id"))
        source_key = show_id or stable_screening_key(movie_url, venue, starts_at)
        screenings.append(
            HiffScreeningData(
                source_key=source_key,
                movie_url=movie_url,
                venue=venue,
                starts_at=starts_at,
                ends_at=parse_end_time(start_text, starts_at),
                duration_minutes=duration,
                screening_number=number,
                screening_total=total,
            )
        )
    return titles, screenings


def parse_movie_html(html_text: str, *, base_url: str) -> HiffMoviePage:
    soup = BeautifulSoup(html_text, "html.parser")
    fields: dict[str, str] = {}
    for field in soup.select(".single-program .field"):
        label = element_text(field.select_one(".label"))
        value = element_text(field.select_one(".value"))
        if label and value:
            fields[label.casefold()] = value

    poster = None
    meta_image = soup.select_one('meta[property="og:image"][content]')
    if meta_image is not None:
        poster = urljoin(base_url, str(meta_image.get("content")))

    letterboxd = None
    for link in soup.select('.single-program a[href]'):
        href = urljoin(base_url, str(link.get("href")))
        if urlparse(href).netloc.casefold().endswith("letterboxd.com"):
            letterboxd = film_page_url(href)
            break
    return HiffMoviePage(
        original_title=fields.get("original name"),
        poster_url=poster,
        letterboxd_url=letterboxd,
        release_year=parse_year(fields.get("year")),
    )


def parse_datetime(value: object) -> datetime | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def parse_year(value: str | None) -> int | None:
    if value and re.fullmatch(r"\d{4}", value):
        return int(value)
    return None


def parse_end_time(value: str | None, starts_at: datetime) -> datetime | None:
    match = re.search(r"[–-](\d{1,2})\.(\d{2})", value or "")
    if match is None:
        return None
    result = starts_at.replace(hour=int(match.group(1)), minute=int(match.group(2)))
    return result + timedelta(days=1) if result < starts_at else result


def parse_duration_and_sequence(value: str | None) -> tuple[int | None, int | None, int | None]:
    duration_match = re.search(r"(\d+)\s*min", value or "", re.IGNORECASE)
    sequence_match = re.search(r"(\d+)\s*/\s*(\d+)", value or "")
    return (
        int(duration_match.group(1)) if duration_match else None,
        int(sequence_match.group(1)) if sequence_match else None,
        int(sequence_match.group(2)) if sequence_match else None,
    )


def stable_screening_key(movie_url: str, venue: str, starts_at: datetime) -> str:
    value = f"{movie_url}|{venue}|{starts_at.isoformat()}".encode()
    return hashlib.sha256(value).hexdigest()


def letterboxd_search_url(title: str) -> str:
    return f"https://letterboxd.com/search/films/{quote(title, safe='')}/"


def clean_text(value: object) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def element_text(element: object) -> str | None:
    if element is None:
        return None
    return clean_text(element.get_text(" ", strip=True))
