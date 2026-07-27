"""
Initialize SQLite database: tạo schema + populate dim_date.

Usage:
    python scripts/init_db.py

Idempotent: chạy nhiều lần không phá dữ liệu.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure project root on sys.path khi chạy trực tiếp file này
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from config import SQLITE_PATH, LOG_LEVEL, ensure_dirs
from src.storage.db import init_schema, get_connection

# Cấu hình logger
logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)


# Dim_date: 5 năm lịch sử + 1 năm tới (cho projection trong dashboard)
DATE_RANGE_START = date.today().replace(month=1, day=1) - timedelta(days=365 * 2)
DATE_RANGE_END = date.today().replace(month=12, day=31) + timedelta(days=365)


def populate_dim_date() -> int:
    """Populate dim_date với daily rows từ DATE_RANGE_START → DATE_RANGE_END.
    Uses INSERT OR IGNORE để idempotent."""
    rows = []
    d = DATE_RANGE_START
    while d <= DATE_RANGE_END:
        iso = d.isoformat()
        # day_of_week: Python weekday() = 0 (Mon) .. 6 (Sun) — match schema comment
        dow = d.weekday()
        rows.append((
            iso,
            d.year,
            (d.month - 1) // 3 + 1,   # quarter 1..4
            d.month,
            dow,
            1 if dow >= 5 else 0,     # Sat=5, Sun=6
        ))
        d += timedelta(days=1)

    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO dim_date
                (date, year, quarter, month, day_of_week, is_weekend)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def main() -> int:
    logger.info(f"Initializing SQLite at: {SQLITE_PATH}")
    ensure_dirs()
    init_schema()
    n_dates = populate_dim_date()
    logger.success(f"✓ Schema created. dim_date populated with {n_dates} rows.")

    # Health check
    from src.storage.db import get_table_rowcounts
    counts = get_table_rowcounts()
    logger.info("Row counts:")
    for t, n in counts.items():
        logger.info(f"  {t:35s} {n:>8d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
