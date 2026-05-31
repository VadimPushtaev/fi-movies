# NytLeffaan Source Research

Research date: 2026-05-31.

Starting point: `https://nytleffaan.fi/paikkakunta/helsinki/`.

## Page Shape

- City pages render movie cards in HTML.
- Movie cards expose title, poster URL, age-limit icon, description, premiere date, and a movie/city URL.
- Movie detail pages embed `currentMovieRawObj`, including richer metadata such as title variants, poster, trailer iframe, age limit, duration, genres, distributor, premiere, description, director, script, and actors.

## Feed Discovery

Movie detail pages also expose JavaScript constants:

- `SHOW_JSON_URI`, for example `/data/shows/shows_2026_05_31_04_32.json?v=61522`
- `API_JSON_URI`, for example `https://nytleffaan.fi/data/apis.json?v=61522`
- `MANUAL_THEATRE_URI`, for example `https://nytleffaan.fi/data/manual_theatre.json?...`

The show JSON filename changes over time, so the scraper should discover it from a movie page instead of hard-coding it.

## Normalized Fields

`shows` rows include:

- `id`
- `theatre_name`
- `api_id`
- `original_movie_title`
- `show_movie_title`
- `show_id`
- `theatre_id`
- `auditorium_name`
- `show_time_start`
- `show_time_end`
- `order_page_url`
- `movie_id`

`movies` rows include:

- `id`
- `movie_id`
- title variants and slug-ish `movie_title_nice`
- poster/trailer URLs
- age limit, duration, genre JSON, distributor, premiere
- `general_info` JSON containing description/director/script/actors

`apis.json` contains source API metadata and theater arrays under keys such as `areas` and `stores`.

## Caveats

- The shows feed can contain duplicate rows for the same showing. Some duplicates use an internal movie ID while others use the canonical movie ID. Normalize internal IDs through the movies list and dedupe showtimes after that.
- Some rows have midnight `00:00` placeholders; the NytLeffaan frontend filters those out, so this app does the same.
- Manual theater data can identify movie/theater availability without exact showtimes. It is imported as theater metadata only for v1.

