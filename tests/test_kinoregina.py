from datetime import datetime

from fi_movies.scrapers.kinoregina import normalize_showtime_html


def test_normalize_kinoregina_showtime_html() -> None:
    html = """
    <div class="row">
      <div class="movie pr col-12 green">
        <div class="content-container d-md-flex col-12">
          <div class="left-side d-md-flex">
            <div class="img-container sixteen-nine cover d-none d-md-inline-block"
                 style="background-image: url('https://kinoregina.fi/wp-content/uploads/2022/01/8-ja-1-2-300x222-optimized.jpg"></div>
            <div class="movie-content d-flex d-md-block pr">
              <span class="time d-block d-md-inline-block">15:30</span>
              <a href="https://kinoregina.fi/elokuva/192590" class="title d-block d-md-inline-block">8½</a>
              <p class="d-none d-md-block">Federico Fellinin omaelämäkerrallinen komedia.</p>
            </div>
          </div>
          <div class="right-side d-block d-md-flex">
            <div class="calendar-icon add-to-calendar cp pa addeventatc">
              <span class="start">31-05-2026 15:30</span>
              <span class="timezone">Europe/Helsinki</span>
              <span class="title">8½</span>
            </div>
            <a href="https://kauppa.kavi.fi/fi/events/pwdg/event_buybox/show/69779d8ce9943694018b4567"
               target="_blank" class="add-to-cart cp pa">Buy</a>
          </div>
        </div>
      </div>
    </div>
    """

    payload = normalize_showtime_html(html, base_url="https://kinoregina.fi")

    assert len(payload.movies) == 1
    assert payload.movies[0].source == "kinoregina"
    assert payload.movies[0].source_movie_id == "192590"
    assert payload.movies[0].title == "8½"
    assert payload.movies[0].description == "Federico Fellinin omaelämäkerrallinen komedia."
    assert payload.movies[0].poster_url == (
        "https://kinoregina.fi/wp-content/uploads/2022/01/8-ja-1-2-300x222-optimized.jpg"
    )
    assert len(payload.theaters) == 1
    assert payload.theaters[0].name == "Kino Regina"
    assert payload.theaters[0].city_slug == "helsinki"
    assert len(payload.showtimes) == 1
    assert payload.showtimes[0].source == "kinoregina"
    assert payload.showtimes[0].source_movie_id == "192590"
    assert payload.showtimes[0].source_theater_id == "kino-regina"
    assert payload.showtimes[0].source_show_id == "69779d8ce9943694018b4567"
    assert payload.showtimes[0].starts_at == datetime(2026, 5, 31, 15, 30)
