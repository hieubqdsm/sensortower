"""
Daily Report Generator — xuất markdown briefing "Daily Briefing — DD/MM".

Output file: reports/YYYY-MM-DD-briefing.md

Cấu trúc report:
  1. Portfolio snapshot (KPIs hiện tại)
  2. Top games (theo Steam CCU hoặc iTunes ranking)
  3. Top news 24h qua (cherry-picked 10 tin hot nhất)
  4. Genre momentum (top trending genres)
  5. Data freshness check (crawler nào chạy hôm nay)
  6. Action items (deals cần review, anomalies)

Usage:
    python scripts/generate_report.py                # hôm nay
    python scripts/generate_report.py --date 2026-07-27
    python scripts/generate_report.py --news-hours 24
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config import PROJECT_ROOT, LOG_LEVEL
from src.storage.db import get_connection

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)


# ---- Report sections -----------------------------------------------------

def section_header(title: str, emoji: str) -> str:
    return f"\n## {emoji} {title}\n"


def section_portfolio(today: str) -> str:
    """Portfolio snapshot KPIs."""
    out = section_header("Portfolio Snapshot", "📊")
    with get_connection() as conn:
        games_total = conn.execute("SELECT COUNT(*) FROM dim_game").fetchone()[0]
        games_steam = conn.execute(
            "SELECT COUNT(*) FROM dim_game WHERE source='steam'"
        ).fetchone()[0]
        games_itunes = conn.execute(
            "SELECT COUNT(*) FROM dim_game WHERE source='itunes'"
        ).fetchone()[0]
        games_igdb = conn.execute(
            "SELECT COUNT(*) FROM dim_game WHERE source='igdb'"
        ).fetchone()[0]
        publishers = conn.execute("SELECT COUNT(*) FROM dim_publisher").fetchone()[0]
        news_24h = conn.execute(
            "SELECT COUNT(*) FROM fact_news WHERE published_at >= datetime('now', '-24 hours')"
        ).fetchone()[0]
        # Freshness
        last_update = conn.execute(
            "SELECT MAX(updated_at) FROM dim_game"
        ).fetchone()[0] or "(chưa có data)"

    out += "| Metric | Value |\n|--------|-------|\n"
    out += f"| Total games tracked | **{games_total}** |\n"
    out += f"| ↳ Steam | {games_steam} |\n"
    out += f"| ↳ iTunes | {games_itunes} |\n"
    out += f"| ↳ IGDB | {games_igdb} |\n"
    out += f"| Publishers | {publishers} |\n"
    out += f"| News (last 24h) | {news_24h} |\n"
    out += f"\n*Last DB update: {last_update}*\n"
    return out


def section_top_games(today: str) -> str:
    """Top games theo CCU (Steam) hoặc ranking (iTunes)."""
    out = section_header("Top Games Today", "🏆")
    with get_connection() as conn:
        # Steam top by CCU
        steam_top = conn.execute(
            """
            SELECT g.name, f.peak_ccu, f.positive_reviews, f.negative_reviews
            FROM fact_steam_playercounts f
            JOIN dim_game g ON f.game_id = g.game_id
            WHERE f.snapshot_date = ?
            ORDER BY f.peak_ccu DESC LIMIT 5
            """,
            (today,),
        ).fetchall()

        # iTunes top ranking (any country/chart)
        itunes_top = conn.execute(
            """
            SELECT g.name, r.country, r.chart_name, r.rank
            FROM fact_itunes_rankings r
            JOIN dim_game g ON r.game_id = g.game_id
            WHERE r.snapshot_date = ? AND r.rank <= 5
            ORDER BY r.country, r.chart_name, r.rank
            LIMIT 10
            """,
            (today,),
        ).fetchall()

    if steam_top:
        out += "### Top Steam (by CCU)\n\n"
        out += "| Rank | Game | Peak CCU | Reviews +/- |\n|------|------|----------|-------------|\n"
        for i, r in enumerate(steam_top, 1):
            out += f"| {i} | {r['name']} | {r['peak_ccu']:,} | {r['positive_reviews']:,}/{r['negative_reviews']:,} |\n"
    else:
        out += "*Steam: chưa có data (chạy `--source steam` để craw)*\n"

    out += "\n"
    if itunes_top:
        out += "### Top iTunes Rankings\n\n"
        out += "| Country | Chart | Rank | Game |\n|---------|-------|------|------|\n"
        for r in itunes_top:
            out += f"| {r['country']} | `{r['chart_name']}` | #{r['rank']} | {r['name']} |\n"
    else:
        out += "*iTunes: chưa có ranking data (game ít khi lọt top overall)*\n"
    return out


def section_top_news(hours: int) -> str:
    """Top news cherry-picked."""
    out = section_header(f"Hot News (Last {hours}h)", "📰")
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT n.title, n.url, s.source_name, n.published_at, n.keywords, n.score
            FROM fact_news n
            JOIN dim_news_source s ON n.source_id = s.source_id
            WHERE n.published_at >= datetime('now', ?)
            ORDER BY COALESCE(n.score, 0) DESC, n.published_at DESC
            LIMIT 15
            """,
            (f"-{hours} hours",),
        ).fetchall()

    if not rows:
        out += f"*Chưa có news trong {hours}h — chạy: `python scripts/run_news.py --hours {hours}`*\n"
        return out

    for i, r in enumerate(rows, 1):
        time_str = datetime.fromisoformat(r["published_at"]).strftime("%H:%M")
        kw = f" `[{r['keywords']}]`" if r["keywords"] else ""
        score = f" ⬆{r['score']}" if r["score"] else ""
        out += f"{i}. **[{time_str}]** `[{r['source_name']}]` [{r['title']}]({r['url']}){kw}{score}\n"
    return out


def section_genre_momentum() -> str:
    """Genre distribution + emerging genres."""
    out = section_header("Genre Distribution", "🎭")
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(genre, '(unknown)') as genre, COUNT(*) as n
            FROM dim_game
            GROUP BY genre ORDER BY n DESC LIMIT 10
            """
        ).fetchall()

    if not rows:
        out += "*Chưa có genre data*\n"
        return out

    out += "| Genre | Games |\n|-------|-------|\n"
    for r in rows:
        out += f"| {r['genre']} | {r['n']} |\n"
    return out


def section_data_quality(today: str) -> str:
    """Check crawler freshness + anomalies."""
    out = section_header("Data Freshness Check", "🔍")
    alerts: list[str] = []

    with get_connection() as conn:
        # Check mỗi source có chạy hôm nay không
        for source in ["steam", "itunes", "igdb"]:
            n = conn.execute(
                """
                SELECT COUNT(*) FROM dim_game
                WHERE source=? AND DATE(updated_at)=?
                """,
                (source, today),
            ).fetchone()[0]
            status = "✅" if n > 0 else "⚠️"
            out += f"- {status} **{source}**: {n} games updated today\n"
            if n == 0:
                alerts.append(f"`{source}` chưa craw hôm nay")

        # Check news freshness
        n_news = conn.execute(
            "SELECT COUNT(*) FROM fact_news WHERE published_at >= datetime('now', '-24 hours')"
        ).fetchone()[0]
        status = "✅" if n_news > 0 else "⚠️"
        out += f"- {status} **news**: {n_news} items last 24h\n"
        if n_news == 0:
            alerts.append("News chưa craw trong 24h")

        # Check dim_date đầy đủ không
        date_count = conn.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0]
        if date_count < 1000:
            alerts.append(f"dim_date ít rows ({date_count}) — chạy `init_db.py`")

    if alerts:
        out += "\n### ⚠️ Action needed\n"
        for a in alerts:
            out += f"- {a}\n"
    else:
        out += "\n*All systems nominal ✨*\n"
    return out


# ---- Main ----------------------------------------------------------------

@click.command()
@click.option("--date", "report_date", type=str, default=None,
              help="Report date (YYYY-MM-DD), default: today")
@click.option("--news-hours", type=int, default=24,
              help="Lookback cho news section (default: 24h)")
@click.option("--out-dir", type=str, default="reports",
              help="Output directory cho markdown report")
def main(report_date: str | None, news_hours: int, out_dir: str):
    """Generate daily briefing markdown report."""
    d = report_date or date.today().isoformat()
    out_path = PROJECT_ROOT / out_dir
    out_path.mkdir(parents=True, exist_ok=True)
    report_file = out_path / f"{d}-briefing.md"

    logger.info(f"Generating briefing for {d} → {report_file.relative_to(PROJECT_ROOT)}")

    today_dt = datetime.now()
    sections = [
        f"# 🎮 Daily Briefing — {d}\n",
        f"*Generated: {today_dt.isoformat(timespec='seconds')}*\n",
        "---",
        section_portfolio(d),
        section_top_games(d),
        section_top_news(news_hours),
        section_genre_momentum(),
        section_data_quality(d),
        "\n---\n*Generated by `scripts/generate_report.py`*\n",
    ]

    report_md = "\n".join(sections)
    report_file.write_text(report_md, encoding="utf-8")

    logger.success(f"✓ Report generated: {report_file}")
    # Print preview to terminal
    print()
    print(report_md)
    sys.exit(0)


if __name__ == "__main__":
    main()
