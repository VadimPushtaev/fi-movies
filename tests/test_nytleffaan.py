from datetime import date, datetime

from fi_movies.scrapers.nytleffaan import (
    discover_feed_urls,
    first_movie_url,
    normalize_payload,
)


def test_discover_feed_urls_resolves_relative_urls() -> None:
    html = """
    <script>
      const API_JSON_URI = 'https://nytleffaan.fi/data/apis.json?v=1';
      const SHOW_JSON_URI = '/data/shows/shows_2026_05_31_04_32.json?v=1';
      const MANUAL_THEATRE_URI = 'https://nytleffaan.fi/data/manual_theatre.json?v=1';
    </script>
    """

    urls = discover_feed_urls(html, page_url="https://nytleffaan.fi/elokuva/cloud/helsinki/")

    assert urls.shows_url == "https://nytleffaan.fi/data/shows/shows_2026_05_31_04_32.json?v=1"
    assert urls.api_url == "https://nytleffaan.fi/data/apis.json?v=1"
    assert urls.manual_theater_url == "https://nytleffaan.fi/data/manual_theatre.json?v=1"


def test_first_movie_url_from_city_page() -> None:
    html = "<a class='movie-card-movie-link' href='/elokuva/cloud/helsinki'>Osta liput!</a>"

    assert first_movie_url(html, base_url="https://nytleffaan.fi/paikkakunta/helsinki/") == (
        "https://nytleffaan.fi/elokuva/cloud/helsinki"
    )


def test_normalize_payload_dedupes_internal_and_canonical_movie_ids() -> None:
    shows_payload = {
        "movies": [
            {
                "id": 5375,
                "movie_id": 100004413,
                "movie_title": "The Super Mario Galaxy Movie",
                "movie_title_nice": "thesupermariogalaxymovie",
                "premiere": "2026-04-01 00:00:00",
                "age_limit": 7,
                "length": 92,
                "genres": '["animaatio"]',
                "general_info": '{"description":"A movie","director":"Someone"}',
            }
        ],
        "shows": [
            {
                "id": "26767946",
                "show_id": "abc",
                "theatre_id": "3",
                "auditorium_name": "Sali 6",
                "show_time_start": "2026-05-31T12:00:00",
                "show_time_end": "",
                "order_page_url": "https://tickets.example/show",
                "movie_id": "100004413",
            },
            {
                "id": "26767946",
                "show_id": "abc",
                "theatre_id": "3",
                "auditorium_name": "Sali 6",
                "show_time_start": "2026-05-31T12:00:00",
                "show_time_end": "",
                "order_page_url": "https://tickets.example/show",
                "movie_id": "5375",
            },
            {
                "id": "placeholder",
                "show_id": "placeholder",
                "theatre_id": "3",
                "show_time_start": "2026-05-31T00:00:00",
                "movie_id": "100004413",
            },
        ],
    }
    api_payload = [
        {
            "id": 1,
            "areas": [
                {
                    "id": "3",
                    "name": "Finnkino ITIS",
                    "location": "Helsinki",
                    "address": "Itakatu 1",
                    "webpage_url": "https://example.com",
                    "api_id": "1",
                    "latitude": "60.213257",
                    "longitude": "25.085189",
                }
            ],
        }
    ]

    payload = normalize_payload(
        shows_payload=shows_payload,
        api_payload=api_payload,
        manual_payload={},
        base_url="https://nytleffaan.fi",
    )

    assert len(payload.movies) == 1
    assert payload.movies[0].premiere_date == date(2026, 4, 1)
    assert payload.movies[0].genres == ["animaatio"]
    assert len(payload.theaters) == 1
    assert len(payload.showtimes) == 1
    assert payload.showtimes[0].source_movie_id == "100004413"
    assert payload.showtimes[0].starts_at == datetime(2026, 5, 31, 12, 0)

