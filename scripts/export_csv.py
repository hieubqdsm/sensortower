"""
Export SQLite tables → CSV files (cho Power BI / Excel / cloud sync).

Power BI / Excel load CSV trực tiếp. Phù hợp khi:
  - Power BI cùng máy / LAN (share folder)
  - Sync lên cloud (rclone S3/GDrive/Dropbox) rồi pull CSV

Usage:
    python scripts/export_csv.py                   # export all raw tables
    python scripts/export_csv.py --flat            # export pre-joined BI-ready tables
    python scripts/export_csv.py --all             # cả raw + flat
    python scripts/export_csv.py --table fact_gacha_revenue  # 1 table cụ thể

Output: data/processed/*.csv + _manifest.json (metadata)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
import pandas as pd
from loguru import logger

from config import LOG_LEVEL, PROCESSED_DIR, ensure_dirs
from src.storage.db import get_connection

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)


def _get_tables() -> list[str]:
    """List user tables."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [r["name"] for r in rows]


def _export_table(name: str, out_dir: Path) -> dict:
    """Export 1 raw table → CSV. Trả metadata."""
    with get_connection() as conn:
        df = pd.read_sql_query(f"SELECT * FROM {name}", conn)
    out_path = out_dir / f"{name}.csv"
    df.to_csv(out_path, index=False)
    return {
        "table": name,
        "file": str(out_path.relative_to(out_dir.parent)),
        "rows": len(df),
        "columns": list(df.columns),
    }


# Pre-joined flat views (BI-ready, không cần build relationships trong Power BI)
FLAT_QUERIES: dict[str, str] = {
    "gacha_flat": """
        SELECT g.game_id, g.name, g.slug, g.icon_url, g.publisher,
               g.first_seen_month,
               r.snapshot_month, r.rank, r.revenue_usd, r.scope, r.source,
               r.fetched_at
        FROM fact_gacha_revenue r
        JOIN dim_gacha_game g ON r.game_id = g.game_id
        ORDER BY r.snapshot_month DESC, r.rank ASC
    """,
    "news_flat": """
        SELECT n.news_id, n.title, n.url, n.summary, n.author,
               n.published_at, n.score, n.keywords, n.fetched_at,
               s.source_type, s.source_name
        FROM fact_news n
        JOIN dim_news_source s ON n.source_id = s.source_id
        ORDER BY n.published_at DESC
    """,
    "dim_date": "SELECT * FROM dim_date ORDER BY date",
}


def _export_flat(name: str, sql: str, out_dir: Path) -> dict:
    """Export 1 flat pre-joined view → CSV."""
    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn)
    out_path = out_dir / f"{name}.csv"
    df.to_csv(out_path, index=False)
    return {
        "view": name,
        "file": str(out_path.relative_to(out_dir.parent)),
        "rows": len(df),
        "columns": list(df.columns),
    }


@click.command()
@click.option("--flat", is_flag=True, default=False,
              help="Export pre-joined BI-ready flat views (gacha_flat, news_flat, dim_date)")
@click.option("--all", "export_all", is_flag=True, default=False,
              help="Export cả raw tables + flat views")
@click.option("--table", type=str, default=None,
              help="Export 1 table cụ thể (vd: fact_gacha_revenue)")
def main(flat: bool, export_all: bool, table: str | None):
    """Export SQLite → CSV."""
    ensure_dirs()
    out_dir = PROCESSED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    do_raw = export_all or (not flat and table is None) or table is not None
    do_flat = export_all or flat

    if not do_raw and not do_flat:
        do_raw = True  # default: raw tables

    manifest: dict = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(out_dir),
        "files": [],
    }

    if do_raw:
        tables = [table] if table else _get_tables()
        if table and table not in _get_tables():
            logger.error(f"❌ Table '{table}' không tồn  tại. Available: {_get_tables()}")
            sys.exit(1)
        logger.info(f"=== EXPORT RAW TABLES ({len(tables)}) → {out_dir}/ ===")
        for t in tables:
            info = _export_table(t, out_dir)
            manifest["files"].append(info)
            logger.info(f"  ✓ {t}.csv — {info['rows']:,} rows")

    if do_flat:
        logger.info(f"=== EXPORT FLAT VIEWS ({len(FLAT_QUERIES)}) ===")
        for name, sql in FLAT_QUERIES.items():
            info = _export_flat(name, sql, out_dir)
            manifest["files"].append(info)
            logger.info(f"  ✓ {name}.csv — {info['rows']:,} rows")

    # Write manifest
    manifest_path = out_dir / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.success(
        f"DONE: {len(manifest['files'])} files exported → {out_dir}/ | "
        f"manifest: _manifest.json"
    )

    # Summary
    total_rows = sum(f["rows"] for f in manifest["files"])
    logger.info(f"Total rows: {total_rows:,}")
    logger.info(
        f"Power BI: Get Data → CSV → trỏ tới {out_dir}/<file>.csv "
        f"(hoặc share folder qua LAN/cloud)"
    )


if __name__ == "__main__":
    main()
