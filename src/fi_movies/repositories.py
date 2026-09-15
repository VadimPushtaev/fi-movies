from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from fi_movies.models import City, Movie, ScrapeRun, Showtime, Theater
from fi_movies.scrapers.nytleffaan import NormalizedMovie, NormalizedShowtime, NormalizedTheater


@dataclass(frozen=True)
class ImportStats:
    movies: int
    theaters: int
    showtimes: int


def upsert_city(session: Session, *, slug: str, name: str) -> City:
    city = session.scalar(select(City).where(City.slug == slug))
    if city is None:
        city = City(slug=slug, name=name)
        session.add(city)
        session.flush()
    else:
        city.name = name
    return city


def upsert_movie(session: Session, movie: NormalizedMovie) -> Movie:
    existing = session.scalar(
        select(Movie).where(
            and_(Movie.source == movie.source, Movie.source_movie_id == movie.source_movie_id)
        )
    )
    if existing is None:
        existing = Movie(source=movie.source, source_movie_id=movie.source_movie_id, title=movie.title, slug=movie.slug)
        session.add(existing)

    existing.source_internal_id = movie.source_internal_id
    if movie.tmdb_id is not None:
        existing.tmdb_id = movie.tmdb_id
    existing.slug = movie.slug
    existing.title = movie.title
    existing.original_title = movie.original_title
    existing.swedish_title = movie.swedish_title
    existing.poster_url = movie.poster_url
    existing.trailer_url = movie.trailer_url
    existing.age_limit = movie.age_limit
    existing.duration_minutes = movie.duration_minutes
    existing.genres = ", ".join(movie.genres)
    existing.distributor = movie.distributor
    existing.premiere_date = movie.premiere_date
    existing.description = movie.description
    existing.director = movie.director
    existing.script = movie.script
    existing.actors = movie.actors
    existing.raw_url = movie.raw_url
    session.flush()
    return existing


def upsert_theater(session: Session, theater: NormalizedTheater) -> Theater:
    city = upsert_city(session, slug=theater.city_slug, name=theater.city_name)
    existing = session.scalar(
        select(Theater).where(
            and_(Theater.source == theater.source, Theater.source_theater_id == theater.source_theater_id)
        )
    )
    if existing is None:
        existing = Theater(
            source=theater.source,
            source_theater_id=theater.source_theater_id,
            city_id=city.id,
            name=theater.name,
        )
        session.add(existing)

    existing.city_id = city.id
    existing.name = theater.name
    existing.address = theater.address
    existing.webpage_url = theater.webpage_url
    existing.phone_number = theater.phone_number
    existing.email = theater.email
    existing.latitude = theater.latitude
    existing.longitude = theater.longitude
    existing.api_id = theater.api_id
    session.flush()
    return existing


def upsert_showtime(
    session: Session,
    showtime: NormalizedShowtime,
    *,
    movies_by_source_id: dict[str, Movie],
    theaters_by_source_id: dict[str, Theater],
) -> Showtime | None:
    movie = movies_by_source_id.get(showtime.source_movie_id)
    theater = theaters_by_source_id.get(showtime.source_theater_id)
    if movie is None or theater is None:
        return None

    existing = session.scalar(select(Showtime).where(Showtime.source_key == showtime.source_key))
    if existing is None:
        existing = Showtime(
            source=showtime.source,
            source_key=showtime.source_key,
            movie_id=movie.id,
            theater_id=theater.id,
            starts_at=showtime.starts_at,
        )
        session.add(existing)

    existing.source_show_id = showtime.source_show_id
    existing.source_raw_id = showtime.source_raw_id
    existing.movie_id = movie.id
    existing.theater_id = theater.id
    existing.auditorium = showtime.auditorium
    existing.starts_at = showtime.starts_at
    existing.ends_at = showtime.ends_at
    existing.order_page_url = showtime.order_page_url
    session.flush()
    return existing


def import_normalized_data(
    session: Session,
    *,
    movies: Iterable[NormalizedMovie],
    theaters: Iterable[NormalizedTheater],
    showtimes: Iterable[NormalizedShowtime],
) -> ImportStats:
    db_movies = [upsert_movie(session, movie) for movie in movies]
    db_theaters = [upsert_theater(session, theater) for theater in theaters]
    movies_by_source_id = {movie.source_movie_id: movie for movie in db_movies}
    theaters_by_source_id = {theater.source_theater_id: theater for theater in db_theaters}

    imported_showtimes = 0
    for showtime in showtimes:
        if upsert_showtime(
            session,
            showtime,
            movies_by_source_id=movies_by_source_id,
            theaters_by_source_id=theaters_by_source_id,
        ):
            imported_showtimes += 1

    session.commit()
    return ImportStats(len(db_movies), len(db_theaters), imported_showtimes)


def start_scrape_run(session: Session, *, source: str) -> ScrapeRun:
    run = ScrapeRun(source=source, status="running", started_at=datetime.utcnow())
    session.add(run)
    session.commit()
    return run


def finish_scrape_run(
    session: Session,
    run: ScrapeRun,
    *,
    status: str,
    message: str | None,
    stats: ImportStats | None = None,
) -> None:
    run.status = status
    run.finished_at = datetime.utcnow()
    run.message = message
    if stats:
        run.movies_seen = stats.movies
        run.theaters_seen = stats.theaters
        run.showtimes_seen = stats.showtimes
    session.commit()


def list_cities(session: Session) -> list[City]:
    return list(session.scalars(select(City).order_by(City.name)))


def latest_scrape_run(session: Session, *, source: str | None = None) -> ScrapeRun | None:
    statement = select(ScrapeRun)
    if source is not None:
        statement = statement.where(ScrapeRun.source == source)
    return session.scalar(statement.order_by(ScrapeRun.started_at.desc()).limit(1))


def showtimes_for_day(
    session: Session,
    *,
    city_slug: str,
    day: date,
    query: str | None = None,
    start_minute: int | None = None,
    end_minute: int | None = None,
) -> list[Showtime]:
    day_start = datetime.combine(day, time.min)
    day_end = day_start + timedelta(days=1)
    window_start = day_start + timedelta(minutes=start_minute or 0)
    window_end = day_start + timedelta(minutes=end_minute if end_minute is not None else 24 * 60)
    statement: Select[tuple[Showtime]] = (
        select(Showtime)
        .join(Showtime.theater)
        .join(Theater.city)
        .join(Showtime.movie)
        .options(joinedload(Showtime.movie), joinedload(Showtime.theater).joinedload(Theater.city))
        .where(
            City.slug == city_slug,
            Showtime.starts_at >= day_start,
            Showtime.starts_at < day_end,
            Showtime.starts_at >= window_start,
            Showtime.starts_at <= window_end,
        )
        .order_by(Movie.title, Theater.name, Showtime.starts_at)
    )
    if query:
        like = f"%{query.strip()}%"
        statement = statement.where(or_(Movie.title.ilike(like), Theater.name.ilike(like)))
    return list(session.scalars(statement))


def available_dates(session: Session, *, city_slug: str) -> list[date]:
    date_expr = func.date(Showtime.starts_at)
    rows = session.execute(
        select(date_expr)
        .join(Showtime.theater)
        .join(Theater.city)
        .where(City.slug == city_slug)
        .group_by(date_expr)
        .order_by(date_expr)
    )
    return [row[0] for row in rows]
