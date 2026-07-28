"""
Load gacha revenue từ CSV manual → SQLite.

Workflow (mỗi tháng 1 lần):
  1. Mở revenue.ennead.cc (hoặc reddit r/gachagaming monthly thread) trên browser
  2. Copy top 50 rows vào CSV theo format template
     (xem: scripts/manual/gacha_revenue_template.csv)
  3. Chạy: python scripts/manual/load_gacha_revenue.py <file.csv>

CSV format (header bắt buộc):
    month,rank,game,revenue_usd,source_url
    2026-05,1,Love and Deepspace,48975000,https://...
    2026-05,2,Genshin Impact,41665000,https://...

- month: YYYY-MM (vd: 2026-05)
- rank: 1..50
- game: tên game (sẽ auto-create dim_game)
- revenue_usd: số USD (không dấu $, không dấu phẩy)
- source_url: link reddit thread gốc (audit)

Idempotent: chạy lại cùng file không duplicate (UPSERT trên game+month).
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from loguru import logger

from config import LOG_LEVEL, ensure_dirs
from src.storage.db import get_connection, init_schema

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)


def _normalize_revenue(raw: str) -> float | None:
    """Parse revenue value — chấp nhận '$48,975,000' hoặc '48975000' hoặc '48.975M'."""
    if not raw:
        return None
    s = str(raw).strip().replace("$", "").replace(",", "").replace(" ", "")
    if not s or s.upper() == "N/A":
        return None
    # Handle 'M' suffix (millions): "48.975M" → 48975000
    m = re.match(r"^([\d.]+)\s*([MB])?$", s, re.IGNORECASE)
    if not m:
        try:
            return float(s)
        except ValueError:
            return None
    val = float(m.group(1))
    if m.group(2) and m.group(2).upper() == "M":
        val *= 1_000_000
    elif m.group(2) and m.group(2).upper() == "B":
        val *= 1_000_000_000
    return val


def _upsert_game(game_name: str) -> int:
    """UPSERT dim_gacha_game. Trả game_id."""
    slug = re.sub(r"[^\w\s-]", "", game_name.lower().strip())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO dim_gacha_game (name, slug)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET name=excluded.name
            """,
            (game_name.strip(), slug),
        )
        row = conn.execute(
            "SELECT game_id FROM dim_gacha_game WHERE name=?",
            (game_name.strip(),),
        ).fetchone()
        return row["game_id"]


def _upsert_revenue(game_id: int, month: str, rank: int, revenue: float,
                    source_url: str) -> bool:
    """UPSERT fact_gacha_revenue. Trả True nếu insert mới."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM fact_gacha_revenue WHERE game_id=? AND snapshot_month=?",
            (game_id, month),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO fact_gacha_revenue
                (game_id, snapshot_month, rank, revenue_usd, scope, source)
            VALUES (?, ?, ?, ?, 'combined', 'manual')
            ON CONFLICT(game_id, snapshot_month) DO UPDATE SET
                rank=excluded.rank,
                revenue_usd=excluded.revenue_usd,
                fetched_at=datetime('now')
            """,
            (game_id, month, rank, revenue),
        )
        return existing is None


def load_csv(csv_path: Path) -> dict[str, int]:
    """Load 1 CSV file → DB. Trả stats dict."""
    if not csv_path.exists():
        logger.error(f"❌ File không tồn tại: {csv_path}")
        sys.exit(1)

    logger.info(f"=== LOAD GACHA REVENUE CSV: {csv_path.name} ===")
    rows_ok = 0
    rows_skip = 0
    games_added = 0
    facts_inserted = 0
    months_seen: set[str] = set()

    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"month", "rank", "game", "revenue_usd"}
        missing_cols = required - set(reader.fieldnames or [])
        if missing_cols:
            logger.error(
                f"❌ CSV thiếu columns: {missing_cols}. "
                f"Cần ít nhất: {required} (xem template)."
            )
            sys.exit(1)

        for i, row in enumerate(reader, start=2):  # line 2 = first data row
            month = (row.get("month") or "").strip()
            rank_raw = (row.get("rank") or "").strip()
            game = (row.get("game") or "").strip()
            revenue_raw = (row.get("revenue_usd") or "").strip()
            source_url = (row.get("source_url") or "").strip()

            # Validate month format YYYY-MM
            if not re.match(r"^\d{4}-\d{2}$", month):
                logger.warning(f"  line {i}: month sai format '{month}' (cần YYYY-MM) — skip")
                rows_skip += 1
                continue
            # Validate rank
            try:
                rank = int(rank_raw)
                if rank < 1 or rank > 100:
                    raise ValueError
            except ValueError:
                logger.warning(f"  line {i}: rank sai '{rank_raw}' — skip")
                rows_skip += 1
                continue
            # Validate game
            if not game:
                logger.warning(f"  line {i}: game trống — skip")
                rows_skip += 1
                continue
            # Parse revenue
            revenue = _normalize_revenue(revenue_raw)
            if revenue is None or revenue < 0:
                logger.warning(f"  line {i}: revenue không hợp lệ '{revenue_raw}' — skip")
                rows_skip += 1
                continue

            # Check game existed before upsert (to count games_added)
            with get_connection() as conn:
                existed = conn.execute(
                    "SELECT 1 FROM dim_gacha_game WHERE name=?",
                    (game,),
                ).fetchone()
            game_id = _upsert_game(game)
            if not existed:
                games_added += 1
            inserted = _upsert_revenue(game_id, month, rank, revenue, source_url)
            if inserted:
                facts_inserted += 1
            rows_ok += 1
            months_seen.add(month)

    logger.success(
        f"DONE: {rows_ok} rows loaded ({rows_skip} skipped), "
        f"{facts_inserted} new facts, {games_added} new games "
        f"| months: {sorted(months_seen)}"
    )
    return {
        "rows_loaded": rows_ok,
        "rows_skipped": rows_skip,
        "facts_inserted": facts_inserted,
        "games_added": games_added,
        "months": sorted(months_seen),
    }


if __name__ == "__main__":
    ensure_dirs()
    init_schema()

    if len(sys.argv) < 2:
        # No arg → load template (sample data for testing)
        default = Path(__file__).parent / "gacha_revenue_template.csv"
        logger.info(f"Không có arg → load template mặc định: {default.name}")
        csv_file = default
    else:
        csv_file = Path(sys.argv[1]).resolve()

    load_csv(csv_file)

    # Summary
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT snapshot_month) as months,
                   COUNT(DISTINCT game_id) as games,
                   COUNT(*) as facts,
                   ROUND(SUM(revenue_usd)/1e6, 1) as total_musd,
                   MIN(snapshot_month) as first_month,
                   MAX(snapshot_month) as last_month
            FROM fact_gacha_revenue
            """,
        ).fetchone()
    logger.info("=== DB SUMMARY ===")
    logger.info(f"  Range: {row['first_month']} → {row['last_month']} ({row['months']} tháng)")
    logger.info(f"  Games: {row['games']}")
    logger.info(f"  Facts: {row['facts']}")
    logger.info(f"  Total est revenue: ${row['total_musd']}M")
