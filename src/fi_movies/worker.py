from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fi_movies.config import get_settings
from fi_movies.db import SessionLocal
from fi_movies.enrichment import TmdbClient
from fi_movies.repositories import finish_scrape_run, import_normalized_data, start_scrape_run
from fi_movies.scrapers import KinoReginaScraper, KorjaamoKinoScraper, NytLeffaanScraper, RivieraScraper
from fi_movies.scrapers.nytleffaan import NormalizedPayload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def run_once() -> None:
    settings = get_settings()
    nytleffaan = NytLeffaanScraper(base_url=settings.nytleffaan_base_url)
    kinoregina = KinoReginaScraper(base_url=settings.kinoregina_base_url)
    korjaamo = KorjaamoKinoScraper(base_url=settings.korjaamo_base_url)
    riviera = RivieraScraper(base_url=settings.riviera_base_url)
    tmdb = TmdbClient(
        api_key=settings.tmdb_api_key,
        read_access_token=settings.resolved_tmdb_read_access_token,
        language=settings.tmdb_language,
    )

    with SessionLocal() as session:
        run = start_scrape_run(session, source="nytleffaan")
        try:
            payloads = [await nytleffaan.scrape(start_city=settings.nytleffaan_start_city)]
            if settings.kinoregina_enabled:
                today = datetime.now(ZoneInfo("Europe/Helsinki")).date()
                payloads.append(await kinoregina.scrape(start_date=today))
            if settings.korjaamo_enabled:
                payloads.append(await korjaamo.scrape())
            if settings.riviera_enabled:
                payloads.append(await riviera.scrape())
            payload = merge_payloads(payloads)
            movies = await tmdb.enrich_movies(payload.movies)
            stats = import_normalized_data(
                session,
                movies=movies,
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


def merge_payloads(payloads: list[NormalizedPayload]) -> NormalizedPayload:
    movies = []
    theaters = []
    showtimes = []
    for payload in payloads:
        movies.extend(payload.movies)
        theaters.extend(payload.theaters)
        showtimes.extend(payload.showtimes)
    return NormalizedPayload(movies=movies, theaters=theaters, showtimes=showtimes)


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
