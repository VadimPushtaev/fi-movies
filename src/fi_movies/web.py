from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from fi_movies.db import SessionLocal, get_session
from fi_movies.hiff_repository import (
    hiff_dates,
    hiff_screening_count,
    hiff_screenings_for_day,
    hiff_screenings_for_movies,
    mark_interrupted_hiff_scrapes,
    running_hiff_scrape,
)
from fi_movies.hiff_service import run_hiff_scrape
from fi_movies.letterboxd import rating_embed_url
from fi_movies.repositories import (
    available_dates,
    latest_scrape_run,
    list_cities,
    showtimes_for_day,
    start_scrape_run,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initial_task = None
    with SessionLocal() as session:
        mark_interrupted_hiff_scrapes(session)
        if hiff_screening_count(session) == 0:
            run = start_scrape_run(session, source="hiff")
            initial_task = asyncio.create_task(run_hiff_scrape(run.id))
    app.state.hiff_initial_task = initial_task
    yield
    if initial_task is not None and not initial_task.done():
        initial_task.cancel()
        with suppress(asyncio.CancelledError):
            await initial_task


app = FastAPI(title="FI Movies", lifespan=lifespan)
templates = Jinja2Templates(directory="src/fi_movies/templates")
app.mount("/static", StaticFiles(directory="src/fi_movies/static"), name="static")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    session: Session = Depends(get_session),
    city: str = Query(default="helsinki"),
    day: date | None = Query(default=None, alias="date"),
    q: str | None = Query(default=None),
    start_minute: int = Query(default=0, ge=0, le=1440),
    end_minute: int = Query(default=1440, ge=0, le=1440),
) -> HTMLResponse:
    selected_date = day or datetime.now(ZoneInfo("Europe/Helsinki")).date()
    selected_city = city.strip().lower() or "helsinki"
    selected_start_minute = min(start_minute, end_minute)
    selected_end_minute = max(start_minute, end_minute)
    showtimes = showtimes_for_day(
        session,
        city_slug=selected_city,
        day=selected_date,
        query=q,
        start_minute=selected_start_minute,
        end_minute=selected_end_minute,
    )
    grouped = group_showtimes(showtimes)
    cities = list_cities(session)
    dates = available_dates(session, city_slug=selected_city)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "cities": cities,
            "dates": dates,
            "groups": grouped,
            "latest_run": latest_scrape_run(session, source="nytleffaan"),
            "selected_city": selected_city,
            "selected_date": selected_date,
            "query": q or "",
            "selected_start_minute": selected_start_minute,
            "selected_end_minute": selected_end_minute,
            "selected_time_range": format_time_range(selected_start_minute, selected_end_minute),
            "prev_date": selected_date - timedelta(days=1),
            "next_date": selected_date + timedelta(days=1),
            "showtime_count": count_grouped_showtimes(grouped),
        },
    )


@app.get("/hiff", response_class=HTMLResponse)
def hiff_index(
    request: Request,
    session: Session = Depends(get_session),
    day: date | None = Query(default=None, alias="date"),
    started: bool = Query(default=False),
) -> HTMLResponse:
    dates = hiff_dates(session)
    today = datetime.now(ZoneInfo("Europe/Helsinki")).date()
    selected_date = choose_hiff_date(day, dates, today=today)
    screenings = hiff_screenings_for_day(session, selected_date) if selected_date else []
    screenings_by_movie = hiff_screenings_for_movies(session, {item.movie_id for item in screenings})
    alternative_screenings = {
        item.id: [other for other in screenings_by_movie[item.movie_id] if other.id != item.id]
        for item in screenings
    }
    latest_run = latest_scrape_run(session, source="hiff")
    return templates.TemplateResponse(
        request,
        "hiff.html",
        {
            "dates": dates,
            "selected_date": selected_date,
            "screenings": screenings,
            "alternative_screenings": alternative_screenings,
            "latest_run": latest_run,
            "scrape_running": running_hiff_scrape(session) is not None,
            "scrape_started": started,
            "rating_embeds": {
                screening.movie_id: rating_embed_url(screening.movie.letterboxd_url)
                for screening in screenings
            },
        },
    )


@app.post("/hiff/rescrape", response_class=RedirectResponse)
def hiff_rescrape(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if running_hiff_scrape(session) is None:
        run = start_scrape_run(session, source="hiff")
        background_tasks.add_task(run_hiff_scrape, run.id)
    return RedirectResponse(url="/hiff?started=true", status_code=303)


def choose_hiff_date(requested: date | None, dates: list[date], *, today: date) -> date | None:
    if requested in dates:
        return requested
    return next((item for item in dates if item >= today), dates[-1] if dates else None)


def group_showtimes(showtimes: list) -> list[dict]:
    by_movie = {}
    for showtime in showtimes:
        movie_key = canonical_movie_key(showtime.movie)
        movie_entry = by_movie.setdefault(
            movie_key,
            {
                "movie": showtime.movie,
                "tmdb_id": showtime.movie.tmdb_id,
                "showtimes": {},
            },
        )
        if movie_entry["tmdb_id"] is None:
            movie_entry["tmdb_id"] = showtime.movie.tmdb_id
        if movie_quality_score(showtime.movie) > movie_quality_score(movie_entry["movie"]):
            movie_entry["movie"] = showtime.movie
        showtime_key = canonical_showtime_key(showtime)
        existing_showtime = movie_entry["showtimes"].get(showtime_key)
        if existing_showtime is None or showtime_quality_score(showtime) > showtime_quality_score(existing_showtime):
            movie_entry["showtimes"][showtime_key] = showtime

    result = []
    for item in by_movie.values():
        theaters = defaultdict(list)
        for showtime in item["showtimes"].values():
            theaters[showtime.theater].append(showtime)
        film_url = letterboxd_url(item["movie"], tmdb_id=item["tmdb_id"])
        result.append(
            {
                "movie": item["movie"],
                "letterboxd_url": film_url,
                "letterboxd_is_search": item["tmdb_id"] is None,
                "letterboxd_rating_embed_url": rating_embed_url(film_url),
                "theaters": [
                    {"theater": theater, "showtimes": sorted(times, key=lambda show: show.starts_at)}
                    for theater, times in sorted(theaters.items(), key=lambda pair: pair[0].name)
                ],
            }
        )
    return sorted(result, key=lambda item: item["movie"].title.lower())


def letterboxd_url(movie: Any, *, tmdb_id: int | None) -> str:
    if tmdb_id is not None:
        return f"https://letterboxd.com/tmdb/{tmdb_id}/"
    title = movie.original_title or movie.title
    return f"https://letterboxd.com/search/films/{quote(title, safe='')}/"


def count_grouped_showtimes(groups: list[dict]) -> int:
    return sum(len(theater_group["showtimes"]) for group in groups for theater_group in group["theaters"])


def canonical_movie_key(movie: Any) -> str:
    return "|".join(
        [
            normalize_display_value(movie.original_title or movie.title),
            str(movie.duration_minutes or ""),
        ]
    )


def canonical_showtime_key(showtime: Any) -> tuple[Any, ...]:
    if showtime.source_show_id:
        return ("show", normalize_display_value(showtime.source_show_id), showtime.starts_at)
    theater = showtime.theater
    return (
        "visible",
        normalize_display_value(getattr(theater, "name", None)),
        normalize_display_value(getattr(theater, "address", None)),
        showtime.starts_at,
        showtime.order_page_url,
        showtime.source_show_id,
        showtime.source_raw_id,
    )


def showtime_quality_score(showtime: Any) -> tuple[int, int, int, int]:
    return (
        source_priority(showtime.source),
        int(bool(showtime.order_page_url)),
        int(bool(getattr(showtime.theater, "address", None))),
        int(bool(showtime.source_raw_id)),
    )


def source_priority(source: str | None) -> int:
    if source in {"kinoregina", "korjaamo", "riviera"}:
        return 2
    return 1


def movie_quality_score(movie: Any) -> tuple[int, int, int, int, int, int]:
    return (
        int(is_valid_poster_url(movie.poster_url)),
        int(bool(movie.description)),
        int(bool(movie.genres)),
        int(bool(movie.age_limit)),
        int(bool(movie.original_title)),
        int(bool(movie.duration_minutes)),
    )


def is_valid_poster_url(url: str | None) -> bool:
    if not url or any(character.isspace() for character in url):
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and "photo uploaded" not in url.casefold()


def normalize_display_value(value: str | None) -> str:
    return " ".join((value or "").casefold().strip().split())


def format_time_range(start_minute: int, end_minute: int) -> str:
    return f"{format_minute(start_minute)} - {format_minute(end_minute)}"


def format_minute(value: int) -> str:
    if value >= 24 * 60:
        return "24:00"
    hours, minutes = divmod(value, 60)
    return f"{hours:02d}:{minutes:02d}"
