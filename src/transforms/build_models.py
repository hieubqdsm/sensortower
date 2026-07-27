"""
Transform layer — post-processing sau khi crawler insert raw.

Hiện tại crawlers đã insert trực tiếp vào dim_game + fact_*, layer này chỉ làm
post-processing cho dim_publisher (extract unique publisher_name → dim row).

Sau này khi phức tạp hơn (deriving engagement metrics từ raw reviews,
genre mapping chuẩn hóa...) sẽ thêm vào đây.

Principle: transform KHÔNG bao giờ sửa raw layer. Chỉ đọc raw → enrich.
"""
from __future__ import annotations

from loguru import logger

from config import LOG_LEVEL
from src.storage.db import get_connection

logger.remove()
import sys
logger.add(sys.stderr, level=LOG_LEVEL)


def populate_dim_publisher() -> int:
    """
    Extract distinct publisher_name từ dim_game → upsert vào dim_publisher.
    Trả về số publishers unique.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT publisher_name
            FROM dim_game
            WHERE publisher_name IS NOT NULL AND publisher_name != ''
            """
        ).fetchall()
        names = [r["publisher_name"] for r in rows]

        if not names:
            logger.info("[transform] no publishers to insert")
            return 0

        inserted = 0
        for name in names:
            cur = conn.execute(
                """
                INSERT INTO dim_publisher (name) VALUES (?)
                ON CONFLICT(name) DO NOTHING
                """,
                (name,),
            )
            inserted += cur.rowcount

    logger.info(f"[transform] dim_publisher: {len(names)} unique, {inserted} new")
    return len(names)


def run_all_transforms() -> dict[str, int]:
    """Run all post-crawl transforms. Return stats dict."""
    logger.info("[transform] starting post-crawl transforms")
    stats = {
        "publishers": populate_dim_publisher(),
    }
    logger.success(f"[transform] DONE: {stats}")
    return stats


if __name__ == "__main__":
    run_all_transforms()
