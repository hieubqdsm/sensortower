"""
Pipeline scheduler — chạy 1 lệnh, tự gọi crawler theo giờ.

KHÔNG cần cron/crontab/launchd. Chỉ cần để script này chạy trong 1 terminal.
Tự sleep + wake theo lịch.

Usage:
    python scripts/serve_pipeline.py              # chạy lịch mặc định
    python scripts/serve_pipeline.py --once       # chạy 1 lần rồi thoát (test)
    python scripts/serve_pipeline.py --dry-run    # xem lịch, không chạy

Schedule mặc định:
    Mỗi giờ :00  → Steam crawl (top 100 CCU)
    Mỗi giờ :30  → iTunes crawl (US + VN games)
    06:00 hàng ngày → News crawl (RSS gaming + AI + Hacker News)

Logs: logs/pipeline-scheduler.log
"""
from __future__ import annotations

import sys
import time as time_mod
from datetime import datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config import LOG_LEVEL, ensure_dirs, LOGS_DIR

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)
logger.add(
    LOGS_DIR / "pipeline-scheduler.log",
    level=LOG_LEVEL,
    rotation="10 MB",
    retention="30 days",
)


def _run(cmd_desc: str, cmd: list[str]) -> None:
    """Run 1 command, log result."""
    import subprocess
    now = datetime.now().strftime("%H:%M:%S")
    logger.info(f"[{now}] ▶ {cmd_desc}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        # tail output để log ngắn
        out = (result.stdout or "").strip().splitlines()[-5:]
        for line in out:
            logger.info(f"  {line}")
        if result.returncode != 0:
            err = (result.stderr or "").strip().splitlines()[-3:]
            for line in err:
                logger.warning(f"  ⚠ {line}")
        logger.success(f"✓ {cmd_desc} done (exit {result.returncode})")
    except subprocess.TimeoutExpired:
        logger.error(f"✗ {cmd_desc} TIMEOUT (>10min)")
    except Exception as e:
        logger.error(f"✗ {cmd_desc} failed: {e}")


def _should_run_steam(now: datetime) -> bool:
    """Mỗi giờ :00."""
    return now.minute == 0


def _should_run_itunes(now: datetime) -> bool:
    """Mỗi giờ :30."""
    return now.minute == 30


def _should_run_news(now: datetime) -> bool:
    """06:00 hàng ngày."""
    return now.hour == 6 and now.minute == 0


@click.command()
@click.option("--once", is_flag=True, help="Chạy 1 lần rồi thoát (test)")
@click.option("--dry-run", is_flag=True, help="Xem lịch, không chạy")
def main(once: bool, dry_run: bool):
    """Scheduler — tự gọi crawler theo giờ."""
    ensure_dirs()

    logger.info("=" * 60)
    logger.info("🎮 Game BI Pipeline Scheduler")
    logger.info("=" * 60)
    logger.info("Schedule:")
    logger.info("  ⏰ Mỗi giờ :00 → Steam crawl (top 100 CCU)")
    logger.info("  ⏰ Mỗi giờ :30 → iTunes crawl (US + VN games)")
    logger.info("  ⏰ 06:00 daily → News crawl (RSS + AI + Hacker News)")
    logger.info("")

    if dry_run:
        logger.info("DRY RUN — không chạy, chỉ show lịch")
        return

    # Map task → đã chạy lần cuối (tránh chạy 2 lần trong cùng phút)
    last_run: dict[str, str] = {}

    while True:
        now = datetime.now()
        slot = now.strftime("%Y-%m-%d %H:%M")

        # Steam
        if _should_run_steam(now) and last_run.get("steam") != slot:
            last_run["steam"] = slot
            if not dry_run:
                _run("Steam crawl", [
                    str(Path(sys.path[0]).parent / ".venv" / "bin" / "python"),
                    "scripts/run_daily.py", "--source", "steam",
                ])

        # iTunes
        if _should_run_itunes(now) and last_run.get("itunes") != slot:
            last_run["itunes"] = slot
            if not dry_run:
                _run("iTunes crawl", [
                    str(Path(sys.path[0]).parent / ".venv" / "bin" / "python"),
                    "scripts/run_daily.py", "--source", "itunes",
                ])

        # News (daily 6am)
        if _should_run_news(now) and last_run.get("news") != slot:
            last_run["news"] = slot
            if not dry_run:
                _run("News crawl", [
                    str(Path(sys.path[0]).parent / ".venv" / "bin" / "python"),
                    "scripts/run_news.py",
                ])

        if once:
            logger.info("--once mode → exiting")
            break

        # Sleep 30s rồi check lại (đảm bảo không miss :00/:30)
        time_mod.sleep(30)


if __name__ == "__main__":
    main()
