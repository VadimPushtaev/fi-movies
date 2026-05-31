# FI Movies

Poetry-based FastAPI site for browsing movie showtimes in Finland. Data is stored in
PostgreSQL and populated by a separate scraper worker container.

## Run With Docker Compose

```bash
docker compose up --build
```

Open `http://localhost:58000`. The worker scrapes once on startup and then repeats
every `SCRAPE_INTERVAL_SECONDS` seconds.

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
