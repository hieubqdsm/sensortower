"""
Enrich genres cho games có genre generic/missing.

iTunes: genre="Games" (generic) → lookup API → sub-genre (Action, Puzzle, RPG...)
Steam:  genre=NULL → appdetails → first genre

Skip games đã có genre specific (no API call). Idempotent.

Usage:
    python scripts/enrich_genres.py --dry-run     # xem bao nhiêu cần enrich
    python scripts/enrich_genres.py               # enrich all
    python scripts/enrich_genres.py --source itunes
    python scripts/enrich_genres.py --source steam
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config import LOG_LEVEL, ensure_dirs
from src.storage.db import get_connection

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)

# Genres coi là "generic" — cần enrich
GENERIC_GENRES = {"Games", "Entertainment", None, ""}


def _pick_itunes_subgenre(genres: list[str]) -> str | None:
    """
    Từ genres array (vd: ["Games","Action","Casual"]) → pick sub-genre đầu tiên
    KHÔNG phải "Games"/"Entertainment" (generic parents).
    """
    for g in genres:
        if g and g not in ("Games", "Entertainment"):
            return g
    # Fallback: trả "Games" nếu chỉ có generic
    return genres[0] if genres else None


def _games_needing_enrich(source: str) -> list[dict]:
    """Trả games có genre generic/NULL cần enrich."""
    with get_connection() as conn:
        if source == "itunes":
            rows = conn.execute(
                """
                SELECT game_id, source_app_id, name, genre
                FROM dim_game
                WHERE source='itunes' AND (genre IS NULL OR genre IN ('Games','Entertainment',''))
                """
            ).fetchall()
        else:  # steam
            rows = conn.execute(
                """
                SELECT game_id, source_app_id, name, genre
                FROM dim_game
                WHERE source='steam' AND (genre IS NULL OR genre='')
                """
            ).fetchall()
    return [dict(r) for r in rows]


def _update_genre(game_id: int, genre: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE dim_game SET genre=?, updated_at=datetime('now') WHERE game_id=?",
            (genre, game_id),
        )


def enrich_itunes(dry_run: bool = False) -> dict:
    """Enrich iTunes games với sub-genre qua lookup API."""
    from src.crawlers.itunes_crawler import ITunesCrawler

    games = _games_needing_enrich("itunes")
    logger.info(f"[itunes] {len(games)} games cần enrich genre")

    if dry_run or not games:
        return {"total": len(games), "enriched": 0, "skipped": 0, "failed": 0}

    crawler = ITunesCrawler()
    enriched = 0
    failed = 0
    for i, g in enumerate(games, start=1):
        app_id = g["source_app_id"]
        detail = crawler.lookup_app(app_id)
        if not detail:
            logger.warning(f"  [{i}/{len(games)}] lookup {app_id} failed ({g['name']})")
            failed += 1
            continue
        genres = detail.get("genres") or []
        sub = _pick_itunes_subgenre(genres)
        if sub and sub != g["genre"]:
            _update_genre(g["game_id"], sub)
            enriched += 1
            if i % 20 == 0 or i == len(games):
                logger.info(f"  [{i}/{len(games)}] enriched {g['name']} → {sub}")
        else:
            logger.debug(f"  [{i}/{len(games)}] skip {g['name']} (no sub-genre found)")
    logger.success(f"[itunes] DONE: {enriched} enriched, {failed} failed, {len(games)-enriched-failed} unchanged")
    return {"total": len(games), "enriched": enriched, "skipped": len(games) - enriched - failed, "failed": failed}


def enrich_steam(dry_run: bool = False) -> dict:
    """Enrich Steam games với genre qua appdetails API."""
    from src.crawlers.steam_crawler import SteamCrawler

    games = _games_needing_enrich("steam")
    logger.info(f"[steam] {len(games)} games cần enrich genre")

    if dry_run or not games:
        return {"total": len(games), "enriched": 0, "skipped": 0, "failed": 0}

    crawler = SteamCrawler()
    enriched = 0
    failed = 0
    for i, g in enumerate(games, start=1):
        appid = int(g["source_app_id"])
        data = crawler.fetch_app_details(appid)
        if not data:
            logger.warning(f"  [{i}/{len(games)}] appdetails {appid} failed ({g['name']})")
            failed += 1
            continue
        genres = [x.get("description", "") for x in data.get("genres", []) if x.get("description")]
        genre = genres[0] if genres else None
        if genre:
            _update_genre(g["game_id"], genre)
            enriched += 1
            logger.info(f"  [{i}/{len(games)}] enriched {g['name']} → {genre}")
    logger.success(f"[steam] DONE: {enriched} enriched, {failed} failed")
    return {"total": len(games), "enriched": enriched, "skipped": len(games) - enriched - failed, "failed": failed}


@click.command()
@click.option("--source", type=click.Choice(["itunes", "steam", "all"]), default="all")
@click.option("--dry-run", is_flag=True, help="Chỉ show count, không enrich")
def main(source: str, dry_run: bool):
    """Enrich genres cho games generic/missing."""
    ensure_dirs()
    logger.info(f"=== ENRICH GENRES | source={source}, dry_run={dry_run} ===")

    stats = {}
    if source in ("itunes", "all"):
        stats["itunes"] = enrich_itunes(dry_run)
    if source in ("steam", "all"):
        stats["steam"] = enrich_steam(dry_run)

    # Final genre distribution
    with get_connection() as conn:
        logger.info("=== Genre distribution (after enrich) ===")
        rows = conn.execute("""
            SELECT source, genre, COUNT(*) as n
            FROM dim_game GROUP BY source, genre ORDER BY source, n DESC
        """).fetchall()
        current = None
        for r in rows:
            if r["source"] != current:
                current = r["source"]
                print(f"\n  {current.upper()}:")
            print(f"    {r['genre'] or '(NULL)':20s} {r['n']:3d} games")
    print()
    logger.info(f"Stats: {stats}")


if __name__ == "__main__":
    main()
