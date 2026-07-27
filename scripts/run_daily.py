"""
Daily pipeline entry point — dùng cho cron / scheduled task.

Usage:
    python scripts/run_daily.py                    # full run
    python scripts/run_daily.py --source steam     # chỉ chạy 1 source
    python scripts/run_daily.py --max 50           # giới hạn 50 game/source
    python scripts/run_daily.py --skip-init        # bỏ qua init_schema

Exit code:
    0 = success (có thể 1 crawler fail nhưng pipeline vẫn hoàn tất)
    1 = catastrophic failure (schema/init error)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config import (
    LOG_LEVEL, MAX_GAMES_PER_SOURCE,
    STEAM_ENABLED, ITUNES_ENABLED, IGDB_ENABLED,
    validate_credentials, ensure_dirs,
)
from src.storage.db import init_schema
from src.transforms import run_all_transforms

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)


def _run_single(source: str, max_n: int) -> dict:
    """Run một source duy nhất (cho --source flag)."""
    if source == "steam":
        if not STEAM_ENABLED:
            logger.warning("STEAM disabled in .env (STEAM_ENABLED=false)")
            return {"status": "skipped"}
        from src.crawlers.steam_crawler import SteamCrawler
        with SteamCrawler() as c:
            return c.run(max_items=max_n)
    elif source == "itunes":
        if not ITUNES_ENABLED:
            logger.warning("ITUNES disabled in .env")
            return {"status": "skipped"}
        from src.crawlers.itunes_crawler import ITunesCrawler
        with ITunesCrawler() as c:
            return c.run(max_items=max_n)
    elif source == "igdb":
        if not IGDB_ENABLED:
            logger.warning("IGDB disabled in .env")
            return {"status": "skipped"}
        from src.crawlers.igdb_crawler import IGDBCrawler
        with IGDBCrawler() as c:
            return c.run(max_items=max_n)
    else:
        raise click.BadParameter(f"Unknown source: {source}")


@click.command()
@click.option("--source", type=click.Choice(["steam", "itunes", "igdb"]),
              default=None, help="Chỉ chạy 1 source (mặc định: chạy hết)")
@click.option("--max", "max_n", type=int, default=None,
              help=f"Số game/source tối đa (default: {MAX_GAMES_PER_SOURCE})")
@click.option("--skip-init", is_flag=True, default=False,
              help="Bỏ qua init_schema (dùng khi DB đã có schema)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Chỉ check credentials + show plan, không crawl")
def main(source: str | None, max_n: int | None, skip_init: bool, dry_run: bool):
    """Run the daily game-data crawl pipeline."""
    ensure_dirs()
    limit = max_n or MAX_GAMES_PER_SOURCE

    logger.info(f"=== DAILY RUN | source={source or 'ALL'} | max={limit} ===")

    # Validate credentials
    missing = validate_credentials()
    if missing and not dry_run:
        logger.error(f"Missing credentials: {missing}")
        logger.error("Fill .env (see .env.example) or disable corresponding crawler.")
        sys.exit(1)

    if dry_run:
        logger.info("DRY RUN — credentials OK, no actual crawl")
        return

    # Init schema if needed
    if not skip_init:
        logger.info("Ensuring schema exists...")
        init_schema()

    # Run
    if source:
        stats = {source: _run_single(source, limit)}
    else:
        from src.pipeline import run_pipeline
        stats = run_pipeline(max_games_per_source=limit)

    # Always run transforms
    if not dry_run:
        logger.info("Running post-crawl transforms...")
        run_all_transforms()

    logger.info(f"=== FINAL STATS ===")
    for src, st in stats.items():
        logger.info(f"  {src}: {st}")

    logger.success("Daily run finished.")
    sys.exit(0)


if __name__ == "__main__":
    main()
