import pytest

from fi_movies.letterboxd import rating_embed_url


@pytest.mark.parametrize(
    ("film_url", "expected"),
    [
        (
            "https://letterboxd.com/film/la-bola-negra/",
            "https://embed.letterboxd.com/film/la-bola-negra/embed-histogram/"
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
