from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from fi_movies.db import get_session
from fi_movies.repositories import available_dates, latest_scrape_run, list_cities, showtimes_for_day

app = FastAPI(title="FI Movies")
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
) -> HTMLResponse:
    selected_date = day or datetime.now(ZoneInfo("Europe/Helsinki")).date()
    selected_city = city.strip().lower() or "helsinki"
    showtimes = showtimes_for_day(session, city_slug=selected_city, day=selected_date, query=q)
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
            "latest_run": latest_scrape_run(session),
            "selected_city": selected_city,
            "selected_date": selected_date,
            "query": q or "",
            "prev_date": selected_date - timedelta(days=1),
            "next_date": selected_date + timedelta(days=1),
            "showtime_count": len(showtimes),
        },
    )


def group_showtimes(showtimes: list) -> list[dict]:
    by_movie = {}
    for showtime in showtimes:
        movie_entry = by_movie.setdefault(
            showtime.movie.id,
            {
                "movie": showtime.movie,
                "theaters": defaultdict(list),
            },
        )
        movie_entry["theaters"][showtime.theater].append(showtime)

    result = []
    for item in by_movie.values():
        result.append(
            {
                "movie": item["movie"],
                "theaters": [
                    {"theater": theater, "showtimes": sorted(times, key=lambda show: show.starts_at)}
                    for theater, times in sorted(item["theaters"].items(), key=lambda pair: pair[0].name)
                ],
            }
        )
    return sorted(result, key=lambda item: item["movie"].title.lower())
