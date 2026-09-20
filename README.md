# FI Movies

Poetry-based FastAPI site for browsing movie showtimes in Finland. Data is stored in
PostgreSQL and populated by a separate scraper worker container.

## Run With Docker Compose

```bash
docker compose up -d --build
```

Open `http://localhost:58000`. The worker scrapes once on startup and then repeats
every `SCRAPE_INTERVAL_SECONDS` seconds.

The database, web app, and worker restart automatically after crashes and system
reboots, provided Docker starts at boot (`sudo systemctl enable --now docker` on
Linux with systemd). The migration container runs once during startup and exits.
Services intentionally stopped with `docker compose stop` or removed with
`docker compose down` stay stopped until you run `docker compose up -d` again.

View service status with `docker compose ps` and follow logs with
`docker compose logs -f --tail=100`.

The worker imports showtimes from NytLeffaan, Kino Regina, Korjaamo Kino, and Riviera by
default. Disable the extra sources with `KINOREGINA_ENABLED=false` or
`KORJAAMO_ENABLED=false` or `RIVIERA_ENABLED=false` when needed.

To enrich scraped movies with English TMDB titles, descriptions, genres, and
runtimes, put a TMDB read access token in `./TOKEN`:

```bash
printf '%s\n' 'your-token' > TOKEN
docker compose up --build
```

You can also set `TMDB_READ_ACCESS_TOKEN` or `TMDB_API_KEY` explicitly.

Each movie title links to Letterboxd in a new tab. TMDB-enriched movies link directly
to the film; unmatched movies fall back to a title search. The worker populates
these IDs on its next scrape. Direct links use
[Letterboxd's TMDB URL format](https://letterboxd.com/about/faq/#linking-to-films).
Exact Letterboxd matches also show Letterboxd's live weighted rating and rating
histogram beside the movie details, using its
[official ratings embed](https://letterboxd.com/about/embed-our-ratings/).

## HIFF Timetable

Open `http://localhost:58000/hiff` for a separate, locally stored copy of the
[Love & Anarchy timetable](https://hiff.fi/en/love-anarchy/timetable/). On a new
database, the web service imports it once in the background. Later imports happen
only when **Rescrape timetable** is pressed on that page. The import stores films,
screenings, posters, HIFF detail links, and Letterboxd links in PostgreSQL; a failed
refresh leaves the previous timetable intact. Successful refreshes update or add
entries while retaining passed screenings that HIFF has removed from its current
page. Click a screening number (such as
**screening 1/2**) to see the movie's other stored dates and times and jump to one.

By default, Docker Compose exposes the web app on all network interfaces at host
port `58000`. PostgreSQL remains available only on localhost at port `55432`.
Override the ports when needed:

```bash
WEB_HOST_PORT=8000 POSTGRES_HOST_PORT=5432 docker compose up --build
```

## Local Development

```bash
poetry install
alembic upgrade head
poetry run uvicorn fi_movies.web:app --reload
poetry run python -m fi_movies.worker --once
```

Set `DATABASE_URL` when not using the default local PostgreSQL URL.
