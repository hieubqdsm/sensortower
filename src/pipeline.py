"""
Pipeline orchestrator — chạy tuần tự: init schema → crawlers → transforms.

Mỗi crawler chạy độc lập, nếu 1 cái fail thì cái sau vẫn chạy.
Cuối cùng summary log + return stats.

Usage:
    from src.pipeline import run_pipeline
    stats = run_pipeline(max_games_per_source=100)
"""
from __future__ import annotations

import sys
import time
import traceback

from loguru import logger

from config import (
    LOG_LEVEL, MAX_GAMES_PER_SOURCE,
    STEAM_ENABLED, ITUNES_ENABLED, IGDB_ENABLED,
)
from src.storage.db import init_schema, get_table_rowcounts
from src.transforms import run_all_transforms

# Configure logger
logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)


def run_pipeline(max_games_per_source: int | None = None) -> dict[str, dict]:
    """
    Run full pipeline. Return nested dict:
        {
            "steam":  {"games_crawled": N, "facts_inserted": M, "status": "ok"},
            "itunes": {...},
            "igdb":   {...},
            "transform": {...},
        }
    """
    max_n = max_games_per_source or MAX_GAMES_PER_SOURCE
    start = time.monotonic()
    logger.info(f"=== PIPELINE START | max_per_source={max_n} ===")

    # 0. Đảm bảo schema tồn tại (idempotent)
    logger.info("[pipeline] ensuring schema exists")
    init_schema()

    stats: dict[str, dict] = {}

    # 1. Steam
    if STEAM_ENABLED:
        stats["steam"] = _run_one("steam", _run_steam, max_n)
    else:
        logger.info("[pipeline] STEAM disabled, skip")
        stats["steam"] = {"status": "skipped"}

    # 2. iTunes
    if ITUNES_ENABLED:
        stats["itunes"] = _run_one("itunes", _run_itunes, max_n)
    else:
        logger.info("[pipeline] ITUNES disabled, skip")
        stats["itunes"] = {"status": "skipped"}

    # 3. IGDB
    if IGDB_ENABLED:
        stats["igdb"] = _run_one("igdb", _run_igdb, max_n)
    else:
        logger.info("[pipeline] IGDB disabled, skip")
        stats["igdb"] = {"status": "skipped"}

    # 4. Post-crawl transforms
    stats["transform"] = _run_one("transform", lambda _: run_all_transforms(), None)

    # 5. Final summary
    elapsed = time.monotonic() - start
    counts = get_table_rowcounts()
    logger.info(f"=== PIPELINE DONE in {elapsed:.1f}s ===")
    logger.info("Final DB row counts:")
    for t, n in counts.items():
        logger.info(f"  {t:35s} {n:>8d}")
    return stats


def _run_one(name: str, fn, max_n) -> dict:
    """Wrapper: log + isolate failure."""
    t0 = time.monotonic()
    try:
        result = fn(max_n)
        elapsed = time.monotonic() - t0
        if not isinstance(result, dict):
            result = {"result": result}
        result["status"] = "ok"
        result["elapsed_sec"] = round(elapsed, 1)
        logger.success(f"[{name}] completed in {elapsed:.1f}s")
        return result
    except Exception as e:
        logger.error(f"[{name}] FAILED: {e}")
        logger.debug(traceback.format_exc())
        return {"status": "failed", "error": str(e),
                "elapsed_sec": round(time.monotonic() - t0, 1)}


# ---- Per-source runners (lazy import để credential check chỉ khi enable) ---
def _run_steam(max_n: int) -> dict:
    from src.crawlers.steam_crawler import SteamCrawler
    with SteamCrawler() as c:
        return c.run(max_items=max_n)


def _run_itunes(max_n: int) -> dict:
    from src.crawlers.itunes_crawler import ITunesCrawler
    with ITunesCrawler() as c:
        return c.run(max_items=max_n)


def _run_igdb(max_n: int) -> dict:
    from src.crawlers.igdb_crawler import IGDBCrawler
    with IGDBCrawler() as c:
        return c.run(max_items=max_n)


if __name__ == "__main__":
    run_pipeline()
