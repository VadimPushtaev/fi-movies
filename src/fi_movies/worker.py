from __future__ import annotations

import argparse
import asyncio
import logging

from fi_movies.config import get_settings
from fi_movies.db import SessionLocal
from fi_movies.repositories import finish_scrape_run, import_normalized_data, start_scrape_run
from fi_movies.scrapers import NytLeffaanScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def run_once() -> None:
    settings = get_settings()
    scraper = NytLeffaanScraper(base_url=settings.nytleffaan_base_url)

    with SessionLocal() as session:
        run = start_scrape_run(session, source="nytleffaan")
        try:
            payload = await scraper.scrape(start_city=settings.nytleffaan_start_city)
            stats = import_normalized_data(
                session,
                movies=payload.movies,
                theaters=payload.theaters,
                showtimes=payload.showtimes,
            )
        except Exception as exc:
            logger.exception("Scrape failed")
            finish_scrape_run(session, run, status="failed", message=str(exc))
            raise
        else:
            finish_scrape_run(session, run, status="success", message=None, stats=stats)
            logger.info(
                "Imported %s movies, %s theaters, %s showtimes",
                stats.movies,
                stats.theaters,
                stats.showtimes,
            )


async def run_forever() -> None:
    settings = get_settings()
    while True:
        try:
            await run_once()
        except Exception:
            logger.warning("Continuing after failed scrape")
        await asyncio.sleep(settings.scrape_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one scrape and exit")
    args = parser.parse_args()
    if args.once:
        asyncio.run(run_once())
    else:
        asyncio.run(run_forever())


if __name__ == "__main__":
    main()

