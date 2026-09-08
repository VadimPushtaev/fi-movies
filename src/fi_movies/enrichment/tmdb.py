from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Any

import httpx

from fi_movies.scrapers.nytleffaan import NormalizedMovie

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TmdbMovieMetadata:
    title: str | None
    overview: str | None
    genres: list[str]
    runtime: int | None


class TmdbClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        read_access_token: str | None = None,
        language: str = "en-US",
        base_url: str = "https://api.themoviedb.org/3",
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.read_access_token = read_access_token
        self.language = language
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key or self.read_access_token)

    async def enrich_movies(self, movies: list[NormalizedMovie]) -> list[NormalizedMovie]:
        movies = harmonize_duplicate_movies(movies)
        if not self.is_configured:
            return movies

        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            headers=self._headers(),
            transport=self.transport,
        ) as client:
            enriched = []
            cache: dict[tuple[str | None, str, int | None], TmdbMovieMetadata | None] = {}
            for movie in movies:
                try:
                    metadata = await self._metadata_for_movie(client, movie, cache)
                except httpx.HTTPError:
                    logger.exception("TMDB enrichment failed for %s", movie.title)
                    metadata = None
                enriched.append(apply_metadata(movie, metadata))
            return enriched

    async def _metadata_for_movie(
        self,
        client: httpx.AsyncClient,
        movie: NormalizedMovie,
        cache: dict[tuple[str | None, str, int | None], TmdbMovieMetadata | None],
    ) -> TmdbMovieMetadata | None:
        search_year = movie.premiere_date.year if movie.premiere_date else None
        for title in movie_search_titles(movie):
            key = (movie.source_movie_id, title, search_year)
            if key not in cache:
                cache[key] = await self._metadata_for_title(client, title=title, year=search_year)
            if cache[key] is not None:
                return cache[key]
        return None

    async def _metadata_for_title(
        self, client: httpx.AsyncClient, *, title: str, year: int | None
    ) -> TmdbMovieMetadata | None:
        for search_year in (year, None):
            results = await self._search_movies(client, title=title, year=search_year)
            match = best_match(title=title, year=year, results=results)
            if match is None:
                continue
            details = await self._movie_details(client, movie_id=int(match["id"]))
            return metadata_from_details(details)
        return None

    async def _search_movies(
        self, client: httpx.AsyncClient, *, title: str, year: int | None
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "query": title,
            "language": self.language,
            "include_adult": "false",
            "page": 1,
        }
        if year is not None:
            params["primary_release_year"] = year
        response = await client.get("/search/movie", params=self._params(params))
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        return [item for item in results if isinstance(item, dict)]

    async def _movie_details(self, client: httpx.AsyncClient, *, movie_id: int) -> dict[str, Any]:
        response = await client.get(f"/movie/{movie_id}", params=self._params({"language": self.language}))
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _headers(self) -> dict[str, str]:
        if not self.read_access_token:
            return {}
        token = self.read_access_token.removeprefix("Bearer ").strip()
        return {"Authorization": f"Bearer {token}"}

    def _params(self, params: dict[str, str | int]) -> dict[str, str | int]:
        if self.api_key and not self.read_access_token:
            return {**params, "api_key": self.api_key}
        return params


def movie_search_titles(movie: NormalizedMovie) -> list[str]:
    titles = [movie.original_title, movie.title]
    cleaned = [title.strip() for title in titles if title and title.strip()]
    return list(dict.fromkeys(cleaned))


def harmonize_duplicate_movies(movies: list[NormalizedMovie]) -> list[NormalizedMovie]:
    by_title: dict[str, list[NormalizedMovie]] = {}
    for movie in movies:
        by_title.setdefault(normalize_title(movie.title), []).append(movie)

    harmonized = []
    for movie in movies:
        group = by_title[normalize_title(movie.title)]
        harmonized.append(
            replace(
                movie,
                original_title=movie.original_title or first_value(item.original_title for item in group),
                swedish_title=movie.swedish_title or first_value(item.swedish_title for item in group),
                poster_url=movie.poster_url or first_value(item.poster_url for item in group),
                trailer_url=movie.trailer_url or first_value(item.trailer_url for item in group),
                age_limit=movie.age_limit or first_value(item.age_limit for item in group),
                duration_minutes=movie.duration_minutes or first_value(item.duration_minutes for item in group),
                genres=movie.genres or first_value(item.genres for item in group) or [],
                distributor=movie.distributor or first_value(item.distributor for item in group),
                premiere_date=movie.premiere_date or first_value(item.premiere_date for item in group),
                description=movie.description or first_value(item.description for item in group),
                director=movie.director or first_value(item.director for item in group),
                script=movie.script or first_value(item.script for item in group),
                actors=movie.actors or first_value(item.actors for item in group),
            )
        )
    return harmonized


def first_value(values: Any) -> Any | None:
    for value in values:
        if value:
            return value
    return None


def best_match(title: str, year: int | None, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [(match_score(title=title, year=year, result=result), result) for result in results]
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < 0.78:
        return None
    return scored[0][1]


def match_score(title: str, year: int | None, result: dict[str, Any]) -> float:
    expected = normalize_title(title)
    possible_titles = [
        normalize_title(str(result.get("title") or "")),
        normalize_title(str(result.get("original_title") or "")),
    ]
    title_score = max((SequenceMatcher(None, expected, value).ratio() for value in possible_titles), default=0.0)
    release_year = release_year_from_result(result)
    if year is not None and release_year == year:
        title_score += 0.08
    elif year is not None and release_year is not None and abs(release_year - year) > 1:
        title_score -= 0.12
    return min(title_score, 1.0)


def release_year_from_result(result: dict[str, Any]) -> int | None:
    raw = str(result.get("release_date") or "")
    if not re.match(r"^\d{4}", raw):
        return None
    return int(raw[:4])


def metadata_from_details(details: dict[str, Any]) -> TmdbMovieMetadata:
    genres = [
        str(genre["name"]).strip()
        for genre in details.get("genres", [])
        if isinstance(genre, dict) and genre.get("name")
    ]
    runtime = details.get("runtime")
    return TmdbMovieMetadata(
        title=clean_metadata_text(details.get("title")),
        overview=clean_metadata_text(details.get("overview")),
        genres=genres,
        runtime=runtime if isinstance(runtime, int) else None,
    )


def apply_metadata(movie: NormalizedMovie, metadata: TmdbMovieMetadata | None) -> NormalizedMovie:
    if metadata is None:
        return movie
    return replace(
        movie,
        title=metadata.title or movie.title,
        description=metadata.overview or movie.description,
        genres=metadata.genres or movie.genres,
        duration_minutes=metadata.runtime or movie.duration_minutes,
    )


def normalize_title(value: str) -> str:
    normalized = value.lower().translate(
        str.maketrans(
            {
                "¼": " 1 4 ",
                "½": " 1 2 ",
                "¾": " 3 4 ",
                "⅐": " 1 7 ",
                "⅑": " 1 9 ",
                "⅒": " 1 10 ",
                "⅓": " 1 3 ",
                "⅔": " 2 3 ",
                "⅕": " 1 5 ",
                "⅖": " 2 5 ",
                "⅗": " 3 5 ",
                "⅘": " 4 5 ",
                "⅙": " 1 6 ",
                "⅚": " 5 6 ",
                "⅛": " 1 8 ",
                "⅜": " 3 8 ",
                "⅝": " 5 8 ",
                "⅞": " 7 8 ",
            }
        )
    )
    normalized = re.sub(r"(\d)\s*/\s*(\d)", r"\1 \2", normalized)
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def clean_metadata_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None
