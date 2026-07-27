"""
Data Quality Checker — detect anomalies + freshness issues.

Chạy độc lập hoặc integrate vào pipeline. Output:
  - Exit code 0 = OK, 1 = warnings, 2 = critical
  - Print alerts ra terminal (đẹp, màu)
  - Optional: --json để dump cho monitoring system

Checks:
  1. Freshness: crawler nào chưa chạy hôm qua
  2. Completeness: % games thiếu metadata (genre, publisher, price)
  3. Anomaly: Steam CCU = 0 bất thường, reviews âm, rank > 100
  4. Volume: số records hôm nay vs avg 7 ngày (drop > 50% = alert)
  5. Schema integrity: orphaned foreign keys

Usage:
    python scripts/data_quality.py
    python scripts/data_quality.py --json
    python scripts/data_quality.py --strict   # exit 1 nếu bất kỳ warning
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config import LOG_LEVEL
from src.storage.db import get_connection, get_table_rowcounts

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)


# ---- Severity levels -----------------------------------------------------
SEV_INFO = "INFO"
SEV_WARNING = "WARNING"
SEV_CRITICAL = "CRITICAL"


def check_freshness(today: str) -> list[dict]:
    """Crawler nào chưa chạy hôm nay."""
    alerts = []
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    with get_connection() as conn:
        for source in ["steam", "itunes", "igdb"]:
            n_today = conn.execute(
                "SELECT COUNT(*) FROM dim_game WHERE source=? AND DATE(updated_at)=?",
                (source, today),
            ).fetchone()[0]
            n_yest = conn.execute(
                "SELECT COUNT(*) FROM dim_game WHERE source=? AND DATE(updated_at)=?",
                (source, yesterday),
            ).fetchone()[0]
            if n_today == 0 and n_yest > 0:
                alerts.append({
                    "severity": SEV_WARNING,
                    "check": "freshness",
                    "source": source,
                    "msg": f"`{source}` not crawled today ({today}). Last run had {n_yest} games.",
                })
            elif n_today == 0 and n_yest == 0:
                alerts.append({
                    "severity": SEV_INFO,
                    "check": "freshness",
                    "source": source,
                    "msg": f"`{source}` never crawled (no games in DB).",
                })
    return alerts


def check_completeness() -> list[dict]:
    """% games thiếu metadata."""
    alerts = []
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM dim_game").fetchone()[0]
        if total == 0:
            return [{"severity": SEV_INFO, "check": "completeness",
                     "msg": "No games in DB yet."}]
        for field in ["genre", "publisher_name", "release_date", "price_usd"]:
            null_count = conn.execute(
                f"SELECT COUNT(*) FROM dim_game WHERE {field} IS NULL OR {field}=''"
            ).fetchone()[0]
            pct = null_count / total * 100
            if pct > 50:
                sev = SEV_WARNING if pct < 80 else SEV_CRITICAL
                alerts.append({
                    "severity": sev,
                    "check": "completeness",
                    "field": field,
                    "msg": f"`dim_game.{field}` NULL/empty: {null_count}/{total} ({pct:.0f}%)",
                })
            elif pct > 10:
                alerts.append({
                    "severity": SEV_INFO,
                    "check": "completeness",
                    "field": field,
                    "msg": f"`dim_game.{field}` missing: {null_count}/{total} ({pct:.0f}%)",
                })
    return alerts


def check_anomalies() -> list[dict]:
    """Anomaly detection: giá trị bất thường."""
    alerts = []
    today = date.today().isoformat()
    with get_connection() as conn:
        # Steam CCU = 0 hôm nay (lạ vì crawled games phải có CCU > 0)
        zero_ccu = conn.execute(
            """
            SELECT COUNT(*) FROM fact_steam_playercounts
            WHERE snapshot_date=? AND peak_ccu=0
            """,
            (today,),
        ).fetchone()[0]
        if zero_ccu > 0:
            alerts.append({
                "severity": SEV_WARNING,
                "check": "anomaly",
                "msg": f"Steam CCU=0 for {zero_ccu} games today (suspicious).",
            })

        # Reviews âm (data corruption)
        neg_reviews = conn.execute(
            "SELECT COUNT(*) FROM fact_steam_playercounts WHERE negative_reviews < 0"
        ).fetchone()[0]
        if neg_reviews > 0:
            alerts.append({
                "severity": SEV_CRITICAL,
                "check": "anomaly",
                "msg": f"Negative review count <0 for {neg_reviews} rows (data corruption).",
            })

        # iTunes rank > 100 (lệch khỏi top)
        weird_rank = conn.execute(
            """
            SELECT COUNT(*) FROM fact_itunes_rankings
            WHERE snapshot_date=? AND rank > 100
            """,
            (today,),
        ).fetchone()[0]
        if weird_rank > 0:
            alerts.append({
                "severity": SEV_INFO,
                "check": "anomaly",
                "msg": f"iTunes rank >100 for {weird_rank} rows (out of expected top-100).",
            })

    return alerts


def check_volume_drop() -> list[dict]:
    """Volume hôm nay vs avg 7 ngày trước."""
    alerts = []
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    with get_connection() as conn:
        # iTunes rankings volume
        today_n = conn.execute(
            "SELECT COUNT(*) FROM fact_itunes_rankings WHERE snapshot_date=?", (today,)
        ).fetchone()[0]
        avg_7d = conn.execute(
            """
            SELECT AVG(daily_count) FROM (
                SELECT COUNT(*) as daily_count FROM fact_itunes_rankings
                WHERE snapshot_date >= ? AND snapshot_date < ?
                GROUP BY snapshot_date
            )
            """,
            (week_ago, today),
        ).fetchone()[0]
        if avg_7d and today_n < avg_7d * 0.5:
            alerts.append({
                "severity": SEV_WARNING,
                "check": "volume_drop",
                "msg": f"iTunes rankings today={today_n} vs avg7d={avg_7d:.0f} (drop >50%)",
            })
    return alerts


def check_referential_integrity() -> list[dict]:
    """Orphaned foreign keys."""
    alerts = []
    with get_connection() as conn:
        orphan_steam = conn.execute(
            """
            SELECT COUNT(*) FROM fact_steam_playercounts f
            LEFT JOIN dim_game g ON f.game_id=g.game_id
            WHERE g.game_id IS NULL
            """
        ).fetchone()[0]
        if orphan_steam > 0:
            alerts.append({
                "severity": SEV_CRITICAL,
                "check": "integrity",
                "msg": f"{orphan_steam} fact_steam_playercounts rows have orphaned game_id",
            })

        orphan_news = conn.execute(
            """
            SELECT COUNT(*) FROM fact_news n
            LEFT JOIN dim_news_source s ON n.source_id=s.source_id
            WHERE s.source_id IS NULL
            """
        ).fetchone()[0]
        if orphan_news > 0:
            alerts.append({
                "severity": SEV_CRITICAL,
                "check": "integrity",
                "msg": f"{orphan_news} fact_news rows have orphaned source_id",
            })
    return alerts


# ---- Pretty printing -----------------------------------------------------
SEV_EMOJI = {
    SEV_INFO: "ℹ️",
    SEV_WARNING: "⚠️",
    SEV_CRITICAL: "🚨",
}


def print_alerts(alerts: list[dict], table_counts: dict[str, int]) -> None:
    print()
    print("=" * 60)
    print("📋 DATA QUALITY REPORT")
    print("=" * 60)
    print(f"Date: {date.today().isoformat()}")
    print()
    print("📊 Current row counts:")
    for t, n in table_counts.items():
        print(f"   {t:30s} {n:>6d}")
    print()

    if not alerts:
        print("✨ All checks passed. No issues detected.")
        return

    # Group by severity
    by_sev = {SEV_CRITICAL: [], SEV_WARNING: [], SEV_INFO: []}
    for a in alerts:
        by_sev[a["severity"]].append(a)

    for sev in [SEV_CRITICAL, SEV_WARNING, SEV_INFO]:
        if not by_sev[sev]:
            continue
        print(f"{SEV_EMOJI[sev]} {sev} ({len(by_sev[sev])})")
        for a in by_sev[sev]:
            print(f"   [{a['check']}] {a['msg']}")
        print()


@click.command()
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output JSON thay vì pretty print")
@click.option("--strict", is_flag=True, default=False,
              help="Exit 1 nếu có bất kỳ warning/critical")
def main(as_json: bool, strict: bool):
    """Run all data quality checks."""
    today = date.today().isoformat()
    logger.info(f"Running data quality checks for {today}")

    alerts: list[dict] = []
    alerts.extend(check_freshness(today))
    alerts.extend(check_completeness())
    alerts.extend(check_anomalies())
    alerts.extend(check_volume_drop())
    alerts.extend(check_referential_integrity())

    counts = get_table_rowcounts()

    if as_json:
        print(json.dumps({
            "date": today,
            "row_counts": counts,
            "alerts": alerts,
            "summary": {
                "critical": sum(1 for a in alerts if a["severity"] == SEV_CRITICAL),
                "warning": sum(1 for a in alerts if a["severity"] == SEV_WARNING),
                "info": sum(1 for a in alerts if a["severity"] == SEV_INFO),
            },
        }, indent=2, ensure_ascii=False))
    else:
        print_alerts(alerts, counts)

    # Exit code
    has_critical = any(a["severity"] == SEV_CRITICAL for a in alerts)
    has_warning = any(a["severity"] == SEV_WARNING for a in alerts)
    if has_critical:
        sys.exit(2)
    elif strict and has_warning:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
