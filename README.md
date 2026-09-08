# FI Movies

Poetry-based FastAPI site for browsing movie showtimes in Finland. Data is stored in
PostgreSQL and populated by a separate scraper worker container.

## Run With Docker Compose

```bash
docker compose up --build
```

Open `http://localhost:58000`. The worker scrapes once on startup and then repeats
every `SCRAPE_INTERVAL_SECONDS` seconds.

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

By default, Docker Compose exposes the web app on host port `58000` and
PostgreSQL on host port `55432` to avoid common local port conflicts. Override
them when needed:

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
