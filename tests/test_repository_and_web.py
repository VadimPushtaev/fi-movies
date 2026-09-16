from dataclasses import replace
from datetime import date, datetime

import pytest
from bs4 import BeautifulSoup
from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fi_movies.models import Base
from fi_movies.repositories import import_normalized_data, showtimes_for_day, upsert_movie
from fi_movies.scrapers.nytleffaan import NormalizedMovie, NormalizedShowtime, NormalizedTheater
from fi_movies.web import app, group_showtimes, index


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


def test_query_showtimes_can_filter_by_time_window() -> None:
    session = make_session()
    movie, theater, showtime = sample_data()
    late_showtime = replace(
        showtime,
        source_key="show-2",
        source_show_id="def",
        starts_at=datetime(2026, 5, 31, 23, 30),
    )
    import_normalized_data(session, movies=[movie], theaters=[theater], showtimes=[showtime, late_showtime])

    results = showtimes_for_day(
        session,
        city_slug="helsinki",
        day=date(2026, 5, 31),
        start_minute=15 * 60,
        end_minute=23 * 60,
    )

    assert [result.starts_at.strftime("%H:%M") for result in results] == ["18:30"]


@pytest.mark.parametrize("tmdb_id", [None, 123])
def test_index_page_renders_grouped_showtimes(tmdb_id: int | None) -> None:
    session = make_session()
    movie, theater, showtime = sample_data()
    movie = replace(movie, tmdb_id=tmdb_id)
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
    response = index(
        request,
        session,
        city="helsinki",
        day=date(2026, 5, 31),
        q=None,
        start_minute=15 * 60,
        end_minute=23 * 60,
    )

    assert response.status_code == 200
    body = response.body.decode()
    assert "Cloud" in body
    assert "Finnkino ITIS" in body
    assert "18:30" in body
    assert "15:00 - 23:00" in body
    assert 'name="start_minute"' in body
    assert 'name="end_minute"' in body
    assert "22.08.2025" not in body
    link = BeautifulSoup(body, "html.parser").select_one(".movie-card .letterboxd-link")
    assert link is not None
    assert link["href"] == (
        "https://letterboxd.com/tmdb/123/" if tmdb_id else "https://letterboxd.com/search/films/Kuraudo/"
    )
    assert link["target"] == "_blank"
    assert set(link["rel"]) == {"noopener", "noreferrer"}
    assert "Cloud" in link["aria-label"]
    assert link.img["src"].endswith("/static/letterboxd.svg")
    rating = BeautifulSoup(body, "html.parser").select_one(".movie-card .letterboxd-rating")
    if tmdb_id:
        assert rating is not None
        assert rating["src"] == (
            "https://embed.letterboxd.com/tmdb/123/embed-histogram/"
            "?noTitle=true&theme=light&noBackground=true"
        )
        assert "Cloud" in rating["title"]
    else:
        assert rating is None


def test_movie_import_preserves_tmdb_id_when_enrichment_is_unavailable() -> None:
    session = make_session()
    movie, _, _ = sample_data()
    saved = upsert_movie(session, replace(movie, tmdb_id=123))
    session.commit()

    upsert_movie(session, movie)
    session.commit()
    session.refresh(saved)
    assert saved.tmdb_id == 123


def test_group_showtimes_deduplicates_same_movie_from_multiple_sources() -> None:
    session = make_session()
    movie, theater, showtime = sample_data()
    duplicate_movie = replace(
        movie,
        source="riviera",
        tmdb_id=123,
        source_movie_id="200",
        title="Cloud",
        original_title="Kuraudo",
    )
    duplicate_theater = replace(
        theater,
        source="riviera",
        source_theater_id="4",
        name="Riviera",
        address="Harjukatu 2",
    )
    duplicate_showtime = replace(
        showtime,
        source="riviera",
        source_key="show-3",
        source_show_id="ghi",
        source_movie_id="200",
        source_theater_id="4",
        starts_at=datetime(2026, 5, 31, 20, 0),
    )
    import_normalized_data(
        session,
        movies=[movie, duplicate_movie],
        theaters=[theater, duplicate_theater],
        showtimes=[showtime, duplicate_showtime],
    )

    groups = group_showtimes(showtimes_for_day(session, city_slug="helsinki", day=date(2026, 5, 31)))

    assert len(groups) == 1
    assert groups[0]["movie"].title == "Cloud"
    assert groups[0]["letterboxd_url"] == "https://letterboxd.com/tmdb/123/"
    assert [item["theater"].name for item in groups[0]["theaters"]] == ["Finnkino ITIS", "Riviera"]
    assert [
        show.starts_at.strftime("%H:%M")
        for theater_group in groups[0]["theaters"]
        for show in theater_group["showtimes"]
    ] == ["18:30", "20:00"]


def test_group_showtimes_hides_duplicate_source_rows_and_prefers_valid_poster() -> None:
    session = make_session()
    movie, theater, showtime = sample_data()
    bad_movie = replace(
        movie,
        source_movie_id="5353",
        poster_url="https://nytleffaan.fi/Photo Uploaded",
    )
    good_movie = replace(
        movie,
        source_movie_id="100004410",
        poster_url="https://nytleffaan.fi/data/images/100004410.jpg",
    )
    bad_showtime = replace(showtime, source_movie_id="5353")
    duplicate_showtime = replace(
        showtime,
        source_key="show-duplicate",
        source_movie_id="100004410",
    )
    import_normalized_data(
        session,
        movies=[bad_movie, good_movie],
        theaters=[theater],
        showtimes=[bad_showtime, duplicate_showtime],
    )

    groups = group_showtimes(showtimes_for_day(session, city_slug="helsinki", day=date(2026, 5, 31)))

    assert len(groups) == 1
    assert groups[0]["movie"].poster_url == "https://nytleffaan.fi/data/images/100004410.jpg"
    assert len(groups[0]["theaters"]) == 1
    assert [show.starts_at.strftime("%H:%M") for show in groups[0]["theaters"][0]["showtimes"]] == ["18:30"]


def test_group_showtimes_prefers_direct_cinema_source_for_same_show_id() -> None:
    session = make_session()
    movie, theater, showtime = sample_data()
    aggregator_movie = replace(
        movie,
        title="Hamnet",
        original_title="Hamnet",
        source="nytleffaan",
        source_movie_id="5301",
    )
    direct_movie = replace(
        movie,
        title="Hamnet",
        original_title="Hamnet",
        source="riviera",
        source_movie_id="30612",
    )
    aggregator_theater = replace(
        theater,
        source="nytleffaan",
        source_theater_id="70",
        name="Riviera",
        address="Harjukatu 2, 00500 Helsinki",
    )
    direct_theater = replace(
        theater,
        source="riviera",
        source_theater_id="riviera-punavuori",
        name="Riviera",
        address="Telakkakatu 7, 00150 Helsinki",
    )
    aggregator_showtime = replace(
        showtime,
        source="nytleffaan",
        source_key="nytleffaan-hamnet",
        source_show_id="970449",
        source_movie_id="5301",
        source_theater_id="70",
        starts_at=datetime(2026, 6, 4, 18, 30),
        order_page_url="http://tickets.rivieracinemas.fi/websales/show/970449/",
    )
    direct_showtime = replace(
        showtime,
        source="riviera",
        source_key="riviera-hamnet",
        source_show_id="970449",
        source_movie_id="30612",
        source_theater_id="riviera-punavuori",
        starts_at=datetime(2026, 6, 4, 18, 30),
        order_page_url="https://www.rivieracinemas.fi/Event/30612?show=970449#tickets",
    )
    import_normalized_data(
        session,
        movies=[aggregator_movie, direct_movie],
        theaters=[aggregator_theater, direct_theater],
        showtimes=[aggregator_showtime, direct_showtime],
    )

    groups = group_showtimes(showtimes_for_day(session, city_slug="helsinki", day=date(2026, 6, 4)))

    assert len(groups) == 1
    assert len(groups[0]["theaters"]) == 1
    assert groups[0]["theaters"][0]["theater"].address == "Telakkakatu 7, 00150 Helsinki"
    assert [show.starts_at.strftime("%H:%M") for show in groups[0]["theaters"][0]["showtimes"]] == ["18:30"]
