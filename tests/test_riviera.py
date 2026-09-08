from datetime import date, datetime

from fi_movies.scrapers.riviera import listing_dates, normalize_listing_html


def test_riviera_listing_dates_from_filter_options() -> None:
    html = """
    <select class="select-date">
      <option value="">Kaikki päivät</option>
      <option value="01.06.2026">Ma 1.6.2026</option>
      <option value="02.06.2026">Ti 2.6.2026</option>
      <option value="02.06.2026">Duplicate</option>
    </select>
    """

    assert listing_dates(html) == [date(2026, 6, 1), date(2026, 6, 2)]


def test_normalize_riviera_listing_html() -> None:
    html = """
    <ul role="list" class="movielist">
      <li class="movielist__item single-show flex flex-col md:flex-row">
        <div class="flex movielist__item__info">
          <div class="movielist__item__date flex flex-col justify-between">
            <span class="date">Ma 1.6.2026</span>
            <span class="time">17:00</span>
            <span class="location">Punavuori, Sali 1</span>
          </div>
          <div class="movielist__item__details flex flex-col justify-between">
            <a href="/Event/31287" target="_blank" class="movielist__item__title title">
              Paholainen pukeutuu Pradaan 2
            </a>
            <span class="length">Kesto: 2 h 0 min</span>
          </div>
        </div>
        <div class="movielist__item__actions flex-grow flex items-center md:justify-end">
          <a href="/Event/31287?show=970441#tickets" target="_top" class="button white smaller">
            Valitse näytös
          </a>
        </div>
      </li>
      <li class="movielist__item single-show flex flex-col md:flex-row">
        <div class="flex movielist__item__info">
          <div class="movielist__item__date flex flex-col justify-between">
            <span class="date">Ma 1.6.2026</span>
            <span class="time">18:00</span>
            <span class="location">Kallio, Sali 1</span>
          </div>
          <div class="movielist__item__details flex flex-col justify-between">
            <a href="/Event/31222" target="_blank" class="movielist__item__title title">Michael</a>
            <span class="length">Kesto: 2 h 7 min</span>
          </div>
        </div>
        <div class="movielist__item__actions flex-grow flex items-center md:justify-end">
          <a href="/Event/31222?show=970431#tickets" target="_top" class="button white smaller">
            Valitse näytös
          </a>
        </div>
      </li>
    </ul>
    """

    payload = normalize_listing_html(html, base_url="https://www.rivieracinemas.fi")

    assert [movie.source_movie_id for movie in payload.movies] == ["31222", "31287"]
    assert payload.movies[0].title == "Michael"
    assert payload.movies[0].duration_minutes == 127
    assert payload.movies[1].title == "Paholainen pukeutuu Pradaan 2"
    assert payload.movies[1].duration_minutes == 120
    assert [theater.name for theater in payload.theaters] == ["Riviera", "Riviera"]
    assert [showtime.source_show_id for showtime in payload.showtimes] == ["970431", "970441"]
    assert payload.showtimes[0].starts_at == datetime(2026, 6, 1, 18, 0)
    assert payload.showtimes[0].source_theater_id == "riviera-kallio"
    assert payload.showtimes[0].auditorium == "Sali 1"
    assert payload.showtimes[1].starts_at == datetime(2026, 6, 1, 17, 0)
    assert payload.showtimes[1].source_theater_id == "riviera-punavuori"
