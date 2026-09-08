import asyncio
from datetime import date

import httpx

from fi_movies.enrichment.tmdb import TmdbClient
from fi_movies.scrapers.nytleffaan import NormalizedMovie


def movie() -> NormalizedMovie:
    return NormalizedMovie(
        source="nytleffaan",
        source_movie_id="100",
        source_internal_id="1",
        slug="operaatio-ave-maria",
        title="Operaatio Ave Maria",
        original_title="Project Hail Mary",
        swedish_title=None,
        poster_url="https://example.com/poster.jpg",
        trailer_url=None,
        age_limit="12",
        duration_minutes=157,
        genres=["seikkailu", "scifi", "toiminta"],
        distributor="SF Studios",
        premiere_date=date(2026, 3, 20),
        description="Finnish description",
        director="Phil Lord, Christopher Miller",
        script=None,
        actors=None,
        raw_url="https://example.com/operaatioavemaria",
    )


def movie_8_half() -> NormalizedMovie:
    return NormalizedMovie(
        source="kinoregina",
        source_movie_id="192590",
        source_internal_id=None,
        slug="8",
        title="8½",
        original_title="8½",
        swedish_title=None,
        poster_url=None,
        trailer_url=None,
        age_limit=None,
        duration_minutes=None,
        genres=[],
        distributor=None,
        premiere_date=None,
        description=None,
        director=None,
        script=None,
        actors=None,
        raw_url="https://example.com/8",
    )


def prada_movie(*, source: str, source_movie_id: str, original_title: str | None) -> NormalizedMovie:
    return NormalizedMovie(
        source=source,
        source_movie_id=source_movie_id,
        source_internal_id=None,
        slug="paholainen-pukeutuu-pradaan-2",
        title="Paholainen pukeutuu Pradaan 2",
        original_title=original_title,
        swedish_title=None,
        poster_url="https://example.com/prada.jpg" if original_title else None,
        trailer_url=None,
        age_limit=None,
        duration_minutes=120,
        genres=[],
        distributor=None,
        premiere_date=None,
        description=None,
        director=None,
        script=None,
        actors=None,
        raw_url="https://example.com/prada",
    )


def test_tmdb_enrichment_uses_original_title_and_english_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token"
        if request.url.path.endswith("/search/movie"):
            assert request.url.params["query"] == "Project Hail Mary"
            assert request.url.params["language"] == "en-US"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 123,
                            "title": "Project Hail Mary",
                            "original_title": "Project Hail Mary",
                            "release_date": "2026-03-20",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/movie/123"):
            return httpx.Response(
                200,
                json={
                    "title": "Project Hail Mary",
                    "overview": "A science teacher wakes up alone on a spaceship.",
                    "genres": [{"name": "Science Fiction"}, {"name": "Adventure"}],
                    "runtime": 157,
                },
            )
        raise AssertionError(f"Unexpected TMDB request: {request.url}")

    client = TmdbClient(read_access_token="token", transport=httpx.MockTransport(handler))
    enriched = asyncio.run(client.enrich_movies([movie()]))

    assert enriched[0].title == "Project Hail Mary"
    assert enriched[0].description == "A science teacher wakes up alone on a spaceship."
    assert enriched[0].genres == ["Science Fiction", "Adventure"]


def test_tmdb_enrichment_is_noop_without_credentials() -> None:
    source_movie = movie()
    client = TmdbClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))

    assert asyncio.run(client.enrich_movies([source_movie])) == [source_movie]


def test_tmdb_enrichment_does_not_match_plain_number_to_fraction_title() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search/movie"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 999,
                            "title": "8",
                            "original_title": "8",
                            "release_date": "2019-01-01",
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected TMDB request: {request.url}")

    source_movie = movie_8_half()
    client = TmdbClient(read_access_token="token", transport=httpx.MockTransport(handler))

    assert asyncio.run(client.enrich_movies([source_movie])) == [source_movie]


def test_tmdb_enrichment_reuses_original_title_for_duplicate_local_titles() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search/movie"):
            assert request.url.params["query"] == "The Devil Wears Prada 2"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1228246,
                            "title": "The Devil Wears Prada 2",
                            "original_title": "The Devil Wears Prada 2",
                            "release_date": "2026-05-01",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/movie/1228246"):
            return httpx.Response(
                200,
                json={
                    "title": "The Devil Wears Prada 2",
                    "overview": "Miranda Priestly and Andy Sachs return.",
                    "genres": [{"name": "Comedy"}, {"name": "Drama"}],
                    "runtime": 119,
                },
            )
        raise AssertionError(f"Unexpected TMDB request: {request.url}")

    source_movies = [
        prada_movie(source="nytleffaan", source_movie_id="100004398", original_title="The Devil Wears Prada 2"),
        prada_movie(source="riviera", source_movie_id="31287", original_title=None),
    ]
    client = TmdbClient(read_access_token="token", transport=httpx.MockTransport(handler))
    enriched = asyncio.run(client.enrich_movies(source_movies))

    assert [movie.title for movie in enriched] == ["The Devil Wears Prada 2", "The Devil Wears Prada 2"]
    assert enriched[1].original_title == "The Devil Wears Prada 2"
    assert enriched[1].poster_url == "https://example.com/prada.jpg"
    assert enriched[1].description == "Miranda Priestly and Andy Sachs return."
    assert enriched[1].genres == ["Comedy", "Drama"]
