from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from fi_movies.models import HiffMovie, HiffScreening, ScrapeRun
from fi_movies.repositories import ImportStats
from fi_movies.scrapers.hiff import HiffPayload


def upsert_hiff_timetable(session: Session, payload: HiffPayload) -> ImportStats:
    """Update the scraped timetable without deleting screenings absent from the latest source page."""
    if not payload.movies or not payload.screenings:
        raise ValueError("Refusing to import an empty HIFF timetable")

    source_urls = {item.source_url for item in payload.movies}
    movies_by_url = {
        movie.source_url: movie
        for movie in session.scalars(select(HiffMovie).where(HiffMovie.source_url.in_(source_urls)))
    }
    for item in payload.movies:
        movie = movies_by_url.get(item.source_url)
        if movie is None:
            movie = HiffMovie(source_url=item.source_url, title=item.title)
            session.add(movie)
            movies_by_url[item.source_url] = movie
        movie.title = item.title
        if item.original_title is not None:
            movie.original_title = item.original_title
        if item.poster_url is not None:
            movie.poster_url = item.poster_url
        if item.letterboxd_url:
            movie.letterboxd_url = item.letterboxd_url
        if item.genres is not None:
            movie.genres = item.genres
    session.flush()

    source_keys = {item.source_key for item in payload.screenings}
    screenings_by_key = {
        screening.source_key: screening
        for screening in session.scalars(
            select(HiffScreening).where(HiffScreening.source_key.in_(source_keys))
        )
    }
    imported = 0
    for item in payload.screenings:
        movie = movies_by_url.get(item.movie_url)
        if movie is None:
            continue
        screening = screenings_by_key.get(item.source_key)
        if screening is None:
            screening = HiffScreening(
                source_key=item.source_key,
                movie_id=movie.id,
                venue=item.venue,
                starts_at=item.starts_at,
            )
            session.add(screening)
            screenings_by_key[item.source_key] = screening
        screening.movie_id = movie.id
        screening.venue = item.venue
        screening.starts_at = item.starts_at
        screening.ends_at = item.ends_at
        screening.duration_minutes = item.duration_minutes
        screening.screening_number = item.screening_number
        screening.screening_total = item.screening_total
        imported += 1
    session.flush()
    return ImportStats(movies=len(payload.movies), theaters=0, showtimes=imported)


def hiff_dates(session: Session) -> list[date]:
    starts = session.scalars(select(HiffScreening.starts_at).order_by(HiffScreening.starts_at)).all()
    return sorted({value.date() for value in starts})


def hiff_screenings_for_day(session: Session, day: date) -> list[HiffScreening]:
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=1)
    return list(
        session.scalars(
            select(HiffScreening)
            .options(joinedload(HiffScreening.movie))
            .where(HiffScreening.starts_at >= start, HiffScreening.starts_at < end)
            .order_by(HiffScreening.starts_at, HiffScreening.venue, HiffScreening.id)
        )
    )


def hiff_screenings_for_movies(session: Session, movie_ids: set[int]) -> dict[int, list[HiffScreening]]:
    if not movie_ids:
        return {}
    by_movie: dict[int, list[HiffScreening]] = defaultdict(list)
    screenings = session.scalars(
        select(HiffScreening)
        .where(HiffScreening.movie_id.in_(movie_ids))
        .order_by(HiffScreening.starts_at, HiffScreening.venue, HiffScreening.id)
    )
    for screening in screenings:
        by_movie[screening.movie_id].append(screening)
    return dict(by_movie)


def hiff_screening_count(session: Session) -> int:
    return session.scalar(select(func.count(HiffScreening.id))) or 0


def running_hiff_scrape(session: Session) -> ScrapeRun | None:
    return session.scalar(
        select(ScrapeRun)
        .where(ScrapeRun.source == "hiff", ScrapeRun.status == "running")
        .order_by(ScrapeRun.started_at.desc())
        .limit(1)
    )


def mark_interrupted_hiff_scrapes(session: Session) -> None:
    runs = session.scalars(
        select(ScrapeRun).where(ScrapeRun.source == "hiff", ScrapeRun.status == "running")
    ).all()
    for run in runs:
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.message = "Interrupted by application restart"
    if runs:
        session.commit()
