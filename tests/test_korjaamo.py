from datetime import datetime

from fi_movies.scrapers.korjaamo import normalize_schedule_html


def test_normalize_korjaamo_schedule_html() -> None:
    html = """
    <div class="schedule-card schedule__item">
      <div class="schedule-card__inner">
        <div class="schedule-card__image-container">
          <a href="https://korjaamokino.fi/event/5171/am%C3%A9lie_-_25-vuotisjuhlajulkaisu?theatreAreaID=1007&amp;dt=02.06.2026">
            <figure class="image schedule-card__image">
              <img
                data-srcset="//images.markus.live/mcswebsites.blob.core.windows.net/1057/Event_7347/landscape_fullhd/Amelie.png?width=350&amp;height=200 350w, //images.markus.live/mcswebsites.blob.core.windows.net/1057/Event_7347/landscape_fullhd/Amelie.png?width=700&amp;height=400 700w"
                alt=""
              >
            </figure>
            <div class="tag schedule-card__tag">K-12</div>
          </a>
        </div>
        <div class="schedule-card__content">
          <div class="schedule-card__time-container">
            <time class="schedule-card__time bold" datetime="2026-06-06T18:30:00.0000000">18.30</time>
            <button
              type="button"
              class="js-event-trailer-button"
              data-src="//www.youtube.com/watch?v=rSl1cYY5lJE"
            >Trailer</button>
          </div>
          <div class="schedule-card__info-container">
            <div class="schedule-card__top">
              <div class="schedule-card__title-container">
                <a href="https://korjaamokino.fi/event/5171/am%C3%A9lie_-_25-vuotisjuhlajulkaisu?theatreAreaID=1007&amp;dt=02.06.2026">
                  <p class="schedule-card__title bold">Amélie - 25-vuotisjuhlajulkaisu</p>
                </a>
                <p class="schedule-card__secondary-title bold text-small">Le fabuleux destin d'Amélie Poulain</p>
                <div class="schedule-card__genres bold text-small">
                  <span class="schedule-card__genre">Komedia,</span>
                  <span class="schedule-card__genre">Romantiikka</span>
                </div>
              </div>
              <div class="schedule-card__button-container">
                <a href="https://korjaamokino.fi/websales/show/167996" class="button schedule-card__primary-button">
                  OSTA
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    """

    payload = normalize_schedule_html(html, base_url="https://korjaamokino.fi")

    assert len(payload.movies) == 1
    assert payload.movies[0].source == "korjaamo"
    assert payload.movies[0].source_movie_id == "5171"
    assert payload.movies[0].title == "Amélie - 25-vuotisjuhlajulkaisu"
    assert payload.movies[0].original_title == "Le fabuleux destin d'Amélie Poulain"
    assert payload.movies[0].age_limit == "12"
    assert payload.movies[0].genres == ["Komedia", "Romantiikka"]
    assert payload.movies[0].poster_url == (
        "https://images.markus.live/mcswebsites.blob.core.windows.net/1057/Event_7347/"
        "landscape_fullhd/Amelie.png?width=350&height=200"
    )
    assert payload.movies[0].trailer_url == "https://www.youtube.com/watch?v=rSl1cYY5lJE"
    assert len(payload.theaters) == 1
    assert payload.theaters[0].name == "Korjaamo Kino"
    assert payload.theaters[0].city_slug == "helsinki"
    assert len(payload.showtimes) == 1
    assert payload.showtimes[0].source == "korjaamo"
    assert payload.showtimes[0].source_movie_id == "5171"
    assert payload.showtimes[0].source_theater_id == "korjaamo-kino"
    assert payload.showtimes[0].source_show_id == "167996"
    assert payload.showtimes[0].starts_at == datetime(2026, 6, 6, 18, 30)
