from __future__ import annotations

import logging
from dataclasses import replace

from fi_movies.config import get_settings
from fi_movies.db import SessionLocal
from fi_movies.enrichment import TmdbClient
from fi_movies.hiff_repository import replace_hiff_timetable
from fi_movies.models import ScrapeRun
from fi_movies.repositories import finish_scrape_run
from fi_movies.scrapers.hiff import HiffScraper

logger = logging.getLogger(__name__)


async def run_hiff_scrape(run_id: int) -> None:
    settings = get_settings()
    scraper = HiffScraper(timetable_url=settings.hiff_timetable_url)
    try:
        payload = await scraper.scrape()
        tmdb = TmdbClient(
            api_key=settings.tmdb_api_key,
            read_access_token=settings.resolved_tmdb_read_access_token,
            language=settings.tmdb_language,
        )
        metadata = await tmdb.metadata_for_titles(
            [(movie.original_title or movie.title, movie.release_year) for movie in payload.movies]
        )
        movies = []
        for movie, details in zip(payload.movies, metadata, strict=True):
            letterboxd_url = movie.letterboxd_url
            if details is not None and "/search/films/" in letterboxd_url:
                letterboxd_url = f"https://letterboxd.com/tmdb/{details.tmdb_id}/"
            movies.append(
                replace(
                    movie,
                    poster_url=details.poster_url if details and details.poster_url else movie.poster_url,
                    letterboxd_url=letterboxd_url,
                )
            )
        payload = replace(payload, movies=movies)
        with SessionLocal() as session:
            run = session.get(ScrapeRun, run_id)
            if run is None:
                raise RuntimeError(f"HIFF scrape run {run_id} no longer exists")
            stats = replace_hiff_timetable(session, payload)
            finish_scrape_run(session, run, status="success", message=None, stats=stats)
            logger.info("Imported %s HIFF movies and %s screenings", stats.movies, stats.showtimes)
    except Exception as exc:
        logger.exception("HIFF timetable scrape failed")
        with SessionLocal() as session:
            run = session.get(ScrapeRun, run_id)
            if run is not None:
                finish_scrape_run(session, run, status="failed", message=str(exc))
