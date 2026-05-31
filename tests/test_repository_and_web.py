from datetime import date, datetime

from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fi_movies.models import Base
from fi_movies.repositories import import_normalized_data, showtimes_for_day
from fi_movies.scrapers.nytleffaan import NormalizedMovie, NormalizedShowtime, NormalizedTheater
from fi_movies.web import app, index


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def sample_data():
    movie = NormalizedMovie(
        source="nytleffaan",
        source_movie_id="100",
        source_internal_id="1",
        slug="cloud",
        title="Cloud",
        original_title="Kuraudo",
        swedish_title=None,
        poster_url="https://example.com/poster.jpg",
        trailer_url=None,
        age_limit="16",
        duration_minutes=123,
        genres=["jannitys"],
        distributor="TabiCine",
        premiere_date=date(2025, 8, 22),
        description="Description",
        director="Kiyoshi Kurosawa",
        script=None,
        actors=None,
        raw_url="https://example.com/cloud",
    )
    theater = NormalizedTheater(
        source="nytleffaan",
        source_theater_id="3",
        city_slug="helsinki",
        city_name="Helsinki",
        name="Finnkino ITIS",
        address="Itakatu 1",
        webpage_url="https://example.com",
        phone_number=None,
        email=None,
        latitude=60.2,
        longitude=25.0,
        api_id="1",
    )
    showtime = NormalizedShowtime(
        source="nytleffaan",
        source_key="show-1",
        source_show_id="abc",
        source_raw_id="raw",
        source_movie_id="100",
        source_theater_id="3",
        auditorium="Sali 1",
        starts_at=datetime(2026, 5, 31, 18, 30),
        ends_at=None,
        order_page_url="https://tickets.example",
    )
    return movie, theater, showtime


def test_import_and_query_showtimes() -> None:
    session = make_session()
    movie, theater, showtime = sample_data()

    stats = import_normalized_data(session, movies=[movie], theaters=[theater], showtimes=[showtime])
    results = showtimes_for_day(session, city_slug="helsinki", day=date(2026, 5, 31))

    assert stats.movies == 1
    assert stats.theaters == 1
    assert stats.showtimes == 1
    assert len(results) == 1
    assert results[0].movie.title == "Cloud"
    assert results[0].theater.name == "Finnkino ITIS"


def test_index_page_renders_grouped_showtimes() -> None:
    session = make_session()
    movie, theater, showtime = sample_data()
    import_normalized_data(session, movies=[movie], theaters=[theater], showtimes=[showtime])

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"city=helsinki&date=2026-05-31",
            "router": app.router,
            "app": app,
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    response = index(request, session, city="helsinki", day=date(2026, 5, 31), q=None)

    assert response.status_code == 200
    body = response.body.decode()
    assert "Cloud" in body
    assert "Finnkino ITIS" in body
    assert "18:30" in body
