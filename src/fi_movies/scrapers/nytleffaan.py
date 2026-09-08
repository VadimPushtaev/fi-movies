from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

SOURCE = "nytleffaan"


@dataclass(frozen=True)
class FeedUrls:
    shows_url: str
    api_url: str
    manual_theater_url: str


@dataclass(frozen=True)
class NormalizedMovie:
    source: str
    source_movie_id: str
    source_internal_id: str | None
    slug: str
    title: str
    original_title: str | None
    swedish_title: str | None
    poster_url: str | None
    trailer_url: str | None
    age_limit: str | None
    duration_minutes: int | None
    genres: list[str]
    distributor: str | None
    premiere_date: date | None
    description: str | None
    director: str | None
    script: str | None
    actors: str | None
    raw_url: str | None
    tmdb_id: int | None = None


@dataclass(frozen=True)
class NormalizedTheater:
    source: str
    source_theater_id: str
    city_slug: str
    city_name: str
    name: str
    address: str | None
    webpage_url: str | None
    phone_number: str | None
    email: str | None
    latitude: float | None
    longitude: float | None
    api_id: str | None


@dataclass(frozen=True)
class NormalizedShowtime:
    source: str
    source_key: str
    source_show_id: str | None
    source_raw_id: str | None
    source_movie_id: str
    source_theater_id: str
    auditorium: str | None
    starts_at: datetime
    ends_at: datetime | None
    order_page_url: str | None


@dataclass(frozen=True)
class NormalizedPayload:
    movies: list[NormalizedMovie]
    theaters: list[NormalizedTheater]
    showtimes: list[NormalizedShowtime]


class NytLeffaanScraper:
    def __init__(self, *, base_url: str = "https://nytleffaan.fi", timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def scrape(self, *, start_city: str = "helsinki") -> NormalizedPayload:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
            city_url = f"{self.base_url}/paikkakunta/{start_city.strip('/')}/"
            city_html = await self._get_text(client, city_url)
            feed_page_url = first_movie_url(city_html, base_url=city_url)
            if feed_page_url is None:
                fallback_movies = fallback_movies_from_city_page(city_html, base_url=city_url)
                return NormalizedPayload(movies=fallback_movies, theaters=[], showtimes=[])

            movie_html = await self._get_text(client, feed_page_url)
            urls = discover_feed_urls(movie_html, page_url=feed_page_url)
            shows_payload, api_payload, manual_payload = await self._fetch_payloads(client, urls)
            return normalize_payload(
                shows_payload=shows_payload,
                api_payload=api_payload,
                manual_payload=manual_payload,
                base_url=self.base_url,
            )

    async def _fetch_payloads(
        self, client: httpx.AsyncClient, urls: FeedUrls
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        shows_response, api_response, manual_response = await asyncio_gather_responses(
            client, urls.shows_url, urls.api_url, urls.manual_theater_url
        )
        return shows_response.json(), api_response.json(), manual_response.json()

    async def _get_text(self, client: httpx.AsyncClient, url: str) -> str:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


async def asyncio_gather_responses(
    client: httpx.AsyncClient, *urls: str
) -> tuple[httpx.Response, ...]:
    import asyncio

    responses = await asyncio.gather(*(client.get(url) for url in urls))
    for response in responses:
        response.raise_for_status()
    return tuple(responses)


def discover_feed_urls(html_text: str, *, page_url: str) -> FeedUrls:
    def match_const(name: str) -> str:
        match = re.search(rf"const\s+{name}\s*=\s*['\"]([^'\"]+)['\"]", html_text)
        if not match:
            raise ValueError(f"Could not discover {name} from NytLeffaan page")
        return urljoin(page_url, html.unescape(match.group(1)))

    return FeedUrls(
        shows_url=match_const("SHOW_JSON_URI"),
        api_url=match_const("API_JSON_URI"),
        manual_theater_url=match_const("MANUAL_THEATRE_URI"),
    )


def first_movie_url(html_text: str, *, base_url: str) -> str | None:
    soup = BeautifulSoup(html_text, "html.parser")
    link = soup.select_one("a.movie-card-movie-link[href]")
    if link is None:
        link = soup.select_one("a[href*='/elokuva/'][href]")
    if link is None:
        return None
    return urljoin(base_url, str(link["href"]))


def fallback_movies_from_city_page(html_text: str, *, base_url: str) -> list[NormalizedMovie]:
    soup = BeautifulSoup(html_text, "html.parser")
    movies: list[NormalizedMovie] = []
    for card in soup.select(".movie-list-column"):
        link = card.select_one("a.movie-card-movie-link[href]")
        title = text_or_none(card.select_one("h3"))
        source_movie_id = source_movie_id_from_card(card)
        if title is None or source_movie_id is None:
            continue
        poster = poster_url_from_card(card)
        movies.append(
            NormalizedMovie(
                source=SOURCE,
                source_movie_id=source_movie_id,
                source_internal_id=None,
                slug=slugify(card.get("movie-url-title") or title),
                title=title,
                original_title=None,
                swedish_title=None,
                poster_url=urljoin(base_url, poster) if poster else None,
                trailer_url=None,
                age_limit=age_limit_from_icon(card),
                duration_minutes=None,
                genres=[],
                distributor=None,
                premiere_date=parse_date(text_or_none(card.select_one(".movie-card-premiere-date"))),
                description=text_or_none(card.select_one(".movie-card-description")),
                director=None,
                script=None,
                actors=None,
                raw_url=urljoin(base_url, str(link["href"])) if link else None,
            )
        )
    return movies


def normalize_payload(
    *,
    shows_payload: dict[str, Any],
    api_payload: list[dict[str, Any]],
    manual_payload: dict[str, Any] | list[Any] | None,
    base_url: str,
) -> NormalizedPayload:
    raw_movies = [item for item in shows_payload.get("movies", []) if item.get("movie_id")]
    movie_by_canonical_id = {str(item["movie_id"]): item for item in raw_movies}
    movie_by_internal_id = {str(item["id"]): item for item in raw_movies if item.get("id") is not None}

    movies = [normalize_movie(item, base_url=base_url) for item in raw_movies]
    theaters = normalize_theaters(api_payload, manual_payload)
    theater_ids = {theater.source_theater_id for theater in theaters}
    showtimes: dict[str, NormalizedShowtime] = {}

    for item in shows_payload.get("shows", []):
        normalized_movie_id = resolve_movie_id(
            item.get("movie_id"),
            movie_by_canonical_id=movie_by_canonical_id,
            movie_by_internal_id=movie_by_internal_id,
        )
        if normalized_movie_id is None:
            continue
        source_theater_id = as_str(item.get("theatre_id"))
        if source_theater_id is None or source_theater_id not in theater_ids:
            continue
        normalized = normalize_showtime(item, source_movie_id=normalized_movie_id)
        if normalized is None:
            continue
        showtimes[normalized.source_key] = normalized

    return NormalizedPayload(movies=movies, theaters=theaters, showtimes=sorted(showtimes.values(), key=lambda s: s.source_key))


def normalize_movie(item: dict[str, Any], *, base_url: str) -> NormalizedMovie:
    general_info = parse_general_info(item.get("general_info"))
    source_movie_id = str(item["movie_id"])
    title = clean_text(item.get("movie_title")) or "Untitled"
    return NormalizedMovie(
        source=SOURCE,
        source_movie_id=source_movie_id,
        source_internal_id=as_str(item.get("id")),
        slug=slugify(item.get("movie_title_nice") or title),
        title=title,
        original_title=clean_text(item.get("movie_title_original")),
        swedish_title=clean_text(item.get("movie_title_sve")),
        poster_url=urljoin(base_url, str(item["poster_url"])) if item.get("poster_url") else None,
        trailer_url=extract_trailer_url(item.get("trailer_url")),
        age_limit=as_str(item.get("age_limit")),
        duration_minutes=parse_int(item.get("length")),
        genres=parse_genres(item.get("genres")),
        distributor=clean_text(item.get("distributor")),
        premiere_date=parse_date(as_str(item.get("premiere"))),
        description=clean_text(general_info.get("description")),
        director=clean_text(general_info.get("director")),
        script=clean_text(general_info.get("script")),
        actors=clean_text(general_info.get("actors")),
        raw_url=f"{base_url}/elokuva/{slugify(item.get('movie_title_nice') or title)}",
    )


def normalize_theaters(
    api_payload: list[dict[str, Any]], manual_payload: dict[str, Any] | list[Any] | None
) -> list[NormalizedTheater]:
    raw_theaters: dict[str, dict[str, Any]] = {}
    for api in api_payload:
        for key in ("areas", "stores"):
            for theater in api.get(key) or []:
                source_id = as_str(theater.get("id"))
                if source_id:
                    raw_theaters[source_id] = theater

    if isinstance(manual_payload, dict):
        manual_values = manual_payload.values()
    elif isinstance(manual_payload, list):
        manual_values = manual_payload
    else:
        manual_values = []
    for entry in manual_values:
        theater = entry.get("theatre") if isinstance(entry, dict) else None
        source_id = as_str(theater.get("id")) if isinstance(theater, dict) else None
        if source_id and source_id not in raw_theaters:
            raw_theaters[source_id] = theater

    normalized = []
    for item in raw_theaters.values():
        city_name = clean_text(item.get("location"))
        theater_name = clean_text(item.get("name"))
        source_id = as_str(item.get("id"))
        if not city_name or not theater_name or not source_id:
            continue
        normalized.append(
            NormalizedTheater(
                source=SOURCE,
                source_theater_id=source_id,
                city_slug=slugify(city_name),
                city_name=city_name,
                name=theater_name,
                address=clean_text(item.get("address")),
                webpage_url=clean_text(item.get("webpage_url")),
                phone_number=clean_text(item.get("phone_number")),
                email=clean_text(item.get("email")),
                latitude=parse_float(item.get("latitude")),
                longitude=parse_float(item.get("longitude")),
                api_id=as_str(item.get("api_id")),
            )
        )
    return sorted(normalized, key=lambda theater: (theater.city_name, theater.name))


def normalize_showtime(item: dict[str, Any], *, source_movie_id: str) -> NormalizedShowtime | None:
    starts_at = parse_datetime(item.get("show_time_start"))
    if starts_at is None or (starts_at.hour == 0 and starts_at.minute == 0):
        return None
    source_theater_id = as_str(item.get("theatre_id"))
    if source_theater_id is None:
        return None
    source_show_id = as_str(item.get("show_id"))
    source_raw_id = as_str(item.get("id"))
    order_page_url = clean_text(item.get("order_page_url"))
    key_parts = [
        SOURCE,
        source_show_id or source_raw_id or "",
        source_theater_id,
        source_movie_id,
        starts_at.isoformat(timespec="minutes"),
        order_page_url or "",
    ]
    source_key = hashlib.sha256("|".join(key_parts).encode("utf-8")).hexdigest()
    return NormalizedShowtime(
        source=SOURCE,
        source_key=source_key,
        source_show_id=source_show_id,
        source_raw_id=source_raw_id,
        source_movie_id=source_movie_id,
        source_theater_id=source_theater_id,
        auditorium=clean_text(item.get("auditorium_name")),
        starts_at=starts_at,
        ends_at=parse_datetime(item.get("show_time_end")),
        order_page_url=order_page_url,
    )


def resolve_movie_id(
    raw_movie_id: Any,
    *,
    movie_by_canonical_id: dict[str, dict[str, Any]],
    movie_by_internal_id: dict[str, dict[str, Any]],
) -> str | None:
    raw = as_str(raw_movie_id)
    if raw is None:
        return None
    if raw in movie_by_canonical_id:
        return raw
    if raw in movie_by_internal_id:
        return str(movie_by_internal_id[raw]["movie_id"])
    return None


def parse_general_info(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(html.unescape(str(value)))
    except json.JSONDecodeError:
        return {}


def parse_genres(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    try:
        decoded = json.loads(str(value))
        if isinstance(decoded, list):
            return [clean_text(item) for item in decoded if clean_text(item)]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in str(value).split(",") if part.strip()]


def parse_datetime(value: Any) -> datetime | None:
    raw = as_str(value)
    if not raw:
        return None
    raw = raw.strip().removesuffix("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip().split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def extract_trailer_url(value: Any) -> str | None:
    raw = clean_text(value)
    if not raw:
        return None
    soup = BeautifulSoup(raw, "html.parser")
    iframe = soup.select_one("iframe[src]")
    if iframe:
        return str(iframe["src"])
    return raw


def slugify(value: Any) -> str:
    raw = clean_text(value) or "unknown"
    ascii_text = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-") or "unknown"


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    raw = html.unescape(str(value))
    if "<" in raw and ">" in raw:
        text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    else:
        text = raw
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def text_or_none(element: Any) -> str | None:
    return clean_text(element.get_text(" ", strip=True)) if element else None


def poster_url_from_card(card: Any) -> str | None:
    poster = card.select_one(".paikkakunta-movie-poster")
    if poster is None:
        return None
    style = str(poster.get("style") or "")
    match = re.search(r"url\(['\"]?([^'\")]+)", style)
    return match.group(1) if match else None


def source_movie_id_from_card(card: Any) -> str | None:
    poster = poster_url_from_card(card)
    if poster:
        match = re.search(r"/data/images/([^/_]+)(?:_small)?\.jpg", poster)
        if match:
            return match.group(1)
    return None


def age_limit_from_icon(card: Any) -> str | None:
    icon = card.select_one("img.movie-card-age-limit-icon[src]")
    if icon is None:
        return None
    match = re.search(r"/icons/([^/.]+)\.png", str(icon["src"]))
    return match.group(1) if match else None
