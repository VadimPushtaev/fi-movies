from datetime import date, datetime

from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from fi_movies.hiff_repository import (
    hiff_dates,
    hiff_screenings_for_day,
    hiff_screenings_for_movies,
    replace_hiff_timetable,
)
from fi_movies.models import Base
from fi_movies.scrapers.hiff import HiffMovieData, HiffPayload, HiffScreeningData, parse_movie_html, parse_timetable_html
from fi_movies.web import app, choose_hiff_date, hiff_index


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def timetable_html() -> str:
    return """
    <ul class="events filtered-items">
      <li class="event item" data-day="2026-09-17" data-time="2026-09-17 16:45:00"
          data-title="Opening Gala: La bola negra" data-venue="Bio Rex Lasipalatsi">
        <a href="/en/program/avajaisgaala-la-bola-negra/">
          <div class="start-time">Thu 17.9. at 16.45–19.40
            <span data-show-rec-id="rec-one"></span>
          </div>
          <div class="duration">155 min, 1/2</div>
        </a>
      </li>
      <li class="event item" data-day="2026-09-17" data-time="2026-09-17 20:00:00"
          data-title="Opening Gala: La bola negra" data-venue="Bio Rex Lasipalatsi">
        <a href="/en/program/avajaisgaala-la-bola-negra/">
          <div class="start-time">Thu 17.9. at 20.00–22.55
            <span data-show-rec-id="rec-two"></span>
          </div>
          <div class="duration">155 min, 2/2</div>
        </a>
      </li>
    </ul>
    """


def payload() -> HiffPayload:
    url = "https://hiff.fi/en/program/avajaisgaala-la-bola-negra/"
    return HiffPayload(
        movies=[
            HiffMovieData(
                source_url=url,
                title="Opening Gala: La bola negra",
                original_title="La Bola Negra",
                poster_url="https://hiff.fi/poster.jpg",
                letterboxd_url="https://letterboxd.com/film/la-bola-negra/",
                release_year=2026,
            )
        ],
        screenings=[
            HiffScreeningData(
                source_key="rec-one",
                movie_url=url,
                venue="Bio Rex Lasipalatsi",
                starts_at=datetime(2026, 9, 17, 16, 45),
                ends_at=datetime(2026, 9, 17, 19, 40),
                duration_minutes=155,
                screening_number=1,
                screening_total=2,
            )
        ],
    )


def test_parse_hiff_timetable() -> None:
    titles, screenings = parse_timetable_html(timetable_html(), base_url="https://hiff.fi/timetable/")

    assert titles == {
        "https://hiff.fi/en/program/avajaisgaala-la-bola-negra/": "Opening Gala: La bola negra"
    }
    assert [item.source_key for item in screenings] == ["rec-one", "rec-two"]
    assert screenings[0].starts_at == datetime(2026, 9, 17, 16, 45)
    assert screenings[0].ends_at == datetime(2026, 9, 17, 19, 40)
    assert screenings[0].duration_minutes == 155
    assert (screenings[0].screening_number, screenings[0].screening_total) == (1, 2)


def test_parse_hiff_movie_page() -> None:
    details = parse_movie_html(
        """
        <meta property="og:image" content="/poster.jpg">
        <div class="single-program">
          <div class="field"><div class="label">Original name</div><div class="value">La Bola Negra</div></div>
          <div class="field"><div class="label">Year</div><div class="value">2026</div></div>
          <div class="field"><div class="label">Links</div><div class="value">
            <a href="https://letterboxd.com/film/la-bola-negra/">Letterboxd</a>
          </div></div>
        </div>
        """,
        base_url="https://hiff.fi/en/program/movie/",
    )

    assert details.original_title == "La Bola Negra"
    assert details.poster_url == "https://hiff.fi/poster.jpg"
    assert details.letterboxd_url == "https://letterboxd.com/film/la-bola-negra/"
    assert details.release_year == 2026


def test_store_and_render_hiff_timetable() -> None:
    session = make_session()
    stats = replace_hiff_timetable(session, payload())
    session.commit()

    assert (stats.movies, stats.showtimes) == (1, 1)
    assert hiff_dates(session) == [date(2026, 9, 17)]
    assert hiff_screenings_for_day(session, date(2026, 9, 17))[0].movie.original_title == "La Bola Negra"

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/hiff",
            "headers": [],
            "query_string": b"date=2026-09-17",
            "router": app.router,
            "app": app,
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    response = hiff_index(request, session, day=date(2026, 9, 17), started=False)
    document = BeautifulSoup(response.body, "html.parser")

    assert document.select_one(".hiff-card h3").get_text(strip=True) == "Opening Gala: La bola negra"
    assert document.select_one(".hiff-poster img")["src"] == "https://hiff.fi/poster.jpg"
    title_link = document.select_one(".hiff-card h3 .letterboxd-title-link")
    assert title_link["href"] == "https://letterboxd.com/film/la-bola-negra/"
    assert title_link["target"] == "_blank"
    assert document.select_one(".hiff-card .letterboxd-link") is None
    assert document.select_one(".letterboxd-rating")["src"] == (
        "https://embed.letterboxd.com/film/la-bola-negra/embed-histogram/"
        "?notitle=true&theme=light"
    )
    assert document.select_one('form[action="/hiff/rescrape"] button').get_text(strip=True) == "Rescrape timetable"
    assert "".join(document.select_one(".hiff-time").get_text().split()) == "16:45–19:40"
    assert document.select_one(".screening-alternatives-trigger") is None


def test_screening_label_opens_other_stored_screenings() -> None:
    session = make_session()
    first_payload = payload()
    second = HiffScreeningData(
        source_key="rec-two",
        movie_url=first_payload.movies[0].source_url,
        venue="Cinema Orion",
        starts_at=datetime(2026, 9, 18, 20, 0),
        ends_at=datetime(2026, 9, 18, 22, 55),
        duration_minutes=155,
        screening_number=2,
        screening_total=2,
    )
    replace_hiff_timetable(
        session,
        HiffPayload(movies=first_payload.movies, screenings=[*first_payload.screenings, second]),
    )
    session.commit()
    first = hiff_screenings_for_day(session, date(2026, 9, 17))[0]
    other = hiff_screenings_for_day(session, date(2026, 9, 18))[0]
    assert [item.id for item in hiff_screenings_for_movies(session, {first.movie_id})[first.movie_id]] == [
        first.id,
        other.id,
    ]

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/hiff",
            "headers": [],
            "query_string": b"date=2026-09-17",
            "router": app.router,
            "app": app,
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    response = hiff_index(request, session, day=date(2026, 9, 17), started=False)
    document = BeautifulSoup(response.body, "html.parser")
    trigger = document.select_one(".screening-alternatives-trigger")
    assert trigger.get_text(" ", strip=True) == "screening 1/2"
    assert trigger["popovertarget"] == f"screenings-{first.id}"
    popover = document.select_one(f"#screenings-{first.id}")
    assert popover["popover"] == "auto"
    assert popover["role"] == "dialog"
    link = popover.select_one(".screening-alternatives-list a")
    assert link["href"] == f"/hiff?date=2026-09-18#screening-{other.id}"
    assert link.time["datetime"] == "2026-09-18T20:00:00"
    assert "20:00" in link.get_text()
    assert "Cinema Orion" in link.get_text()
    assert "16:45" not in popover.get_text()


def test_choose_hiff_date_prefers_requested_then_next_festival_day() -> None:
    dates = [date(2026, 9, 17), date(2026, 9, 18)]

    assert choose_hiff_date(date(2026, 9, 18), dates, today=date(2026, 9, 16)) == date(2026, 9, 18)
    assert choose_hiff_date(None, dates, today=date(2026, 9, 16)) == date(2026, 9, 17)
    assert choose_hiff_date(None, dates, today=date(2026, 9, 19)) == date(2026, 9, 18)
