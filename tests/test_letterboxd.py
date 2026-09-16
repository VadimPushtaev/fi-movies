import asyncio

import httpx
import pytest

from fi_movies.letterboxd import fetch_film_genres, parse_film_genres, rating_embed_url


@pytest.mark.parametrize(
    ("film_url", "expected"),
    [
        (
            "https://letterboxd.com/film/la-bola-negra/",
            "https://embed.letterboxd.com/film/la-bola-negra/embed-histogram/"
            "?notitle=true&theme=light",
        ),
        (
            "https://letterboxd.com/film/nox-2026/cast/",
            "https://embed.letterboxd.com/film/nox-2026/embed-histogram/"
            "?notitle=true&theme=light",
        ),
        (
            "https://letterboxd.com/tmdb/123/",
            "https://embed.letterboxd.com/tmdb/123/embed-histogram/"
            "?notitle=true&theme=light",
        ),
        ("https://letterboxd.com/search/films/Cloud/", None),
        ("https://letterboxd.com:444/film/cloud/", None),
        ("https://letterboxd.com/film/cloud/?source=other", None),
        ("https://attacker.example/film/cloud/", None),
        (None, None),
    ],
)
def test_rating_embed_url_uses_only_exact_letterboxd_film_links(film_url, expected) -> None:
    assert rating_embed_url(film_url) == expected


def test_parse_film_genres_excludes_themes_and_duplicate_links() -> None:
    html = """
    <div id="tab-panel-genres">
      <a href="/films/genre/comedy/">Comedy</a>
      <a href="/films/genre/thriller/">Thriller</a>
      <a href="/films/genre/comedy/">Comedy</a>
      <a href="/films/theme/identity/">Identity</a>
    </div>
    """

    assert parse_film_genres(html) == ("Comedy", "Thriller")


def test_fetch_film_genres_ignores_search_links_and_fetches_a_film_once() -> None:
    requested = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            200,
            text='<div id="tab-panel-genres"><a href="/films/genre/drama/">Drama</a></div>',
        )

    film_url = "https://letterboxd.com/film/nox-2026/cast/"
    genres = asyncio.run(
        fetch_film_genres(
            [film_url, film_url, "https://letterboxd.com/search/films/Nox/"],
            transport=httpx.MockTransport(respond),
        )
    )

    assert genres == {film_url: ("Drama",)}
    assert requested == ["https://letterboxd.com/film/nox-2026/"]
