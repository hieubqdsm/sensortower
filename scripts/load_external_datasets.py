"""
Load external datasets vào SQLite + simulate internal KPIs.

Data sources:
- Cookie Cats (90K rows): retention D1/D7 + A/B test — real game data
- VG Sales (16K rows): historical game sales by platform/genre
- Simulated DAU/ARPDAU/IAP: based on industry benchmarks (methodology.md §6)

All tables prefixed 'sample_' — clear label that this is SAMPLE/EXTERNAL data.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from loguru import logger

from config import LOG_LEVEL, PROJECT_ROOT
from src.storage.db import get_connection, init_schema

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)

EXTERNAL_DIR = PROJECT_ROOT / "data" / "external" / "kaggle"

SCHEMA = """
-- =========================================================
-- EXTERNAL / SAMPLE DATASETS (Kaggle + simulated)
-- Label rõ: không phải data thật từ company MMP
-- =========================================================

-- Cookie Cats A/B test: retention D1/D7 (real game data, 90K users)
CREATE TABLE IF NOT EXISTS sample_cookie_cats (
    userid INTEGER PRIMARY KEY,
    version TEXT,
    sum_gamerounds INTEGER,
    retention_1 INTEGER,
    retention_7 INTEGER,
    source TEXT DEFAULT 'Kaggle: Cookie Cats A/B Test'
);

-- Video Game Sales: historical sales (16K games, 1980-2020)
CREATE TABLE IF NOT EXISTS sample_vgsales (
    rank INTEGER PRIMARY KEY,
    name TEXT,
    platform TEXT,
    year INTEGER,
    genre TEXT,
    publisher TEXT,
    na_sales REAL,
    eu_sales REAL,
    jp_sales REAL,
    other_sales REAL,
    global_sales REAL,
    source TEXT DEFAULT 'Kaggle: Video Game Sales'
);

-- Simulated DAU/MAU/ARPDAU daily (based on industry benchmarks)
CREATE TABLE IF NOT EXISTS sample_daily_kpis (
    kpi_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_name TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    genre TEXT,
    dau INTEGER,
    mau INTEGER,
    arpdau REAL,
    arpu REAL,
    d1_retention REAL,
    d7_retention REAL,
    d30_retention REAL,
    iap_conversion_pct REAL,
    crash_rate_pct REAL,
    source TEXT DEFAULT 'SIMULATED from industry benchmarks',
    UNIQUE(game_name, snapshot_date)
);

-- Simulated UA campaign data (CPI/CTR/CVR/spend/installs)
CREATE TABLE IF NOT EXISTS sample_ua_campaigns (
    ua_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_name TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    region TEXT,
    ad_network TEXT,
    impressions INTEGER,
    clicks INTEGER,
    installs INTEGER,
    spend_usd REAL,
    cpi REAL,
    ctr REAL,
    cvr REAL,
    roas_d7 REAL,
    roas_d30 REAL,
    source TEXT DEFAULT 'SIMULATED from gacha revenue + benchmarks',
    UNIQUE(game_name, snapshot_date, region, ad_network)
);
"""


def apply_schema():
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    logger.info("✓ External sample tables created")


def load_cookie_cats():
    path = EXTERNAL_DIR / "cookie_cats.csv"
    if not path.exists():
        logger.warning(f"Cookie Cats not found: {path}")
        return 0
    df = pd.read_csv(path)
    # Convert boolean to int
    df["retention_1"] = df["retention_1"].astype(int)
    df["retention_7"] = df["retention_7"].astype(int)
    with get_connection() as conn:
        conn.execute("DELETE FROM sample_cookie_cats")
        df.to_sql("sample_cookie_cats", conn, if_exists="append", index=False)
    logger.info(f"✓ Cookie Cats: {len(df)} rows loaded")
    return len(df)


def load_vgsales():
    path = EXTERNAL_DIR / "vgsales.csv"
    if not path.exists():
        logger.warning(f"VG Sales not found: {path}")
        return 0
    df = pd.read_csv(path)
    with get_connection() as conn:
        conn.execute("DELETE FROM sample_vgsales")
        df.to_sql("sample_vgsales", conn, if_exists="append", index=False)
    logger.info(f"✓ VG Sales: {len(df)} rows loaded")
    return len(df)


def simulate_daily_kpis():
    """
    Simulate DAU/MAU/ARPDAU/Retention/IAP/Crash rate cho top gacha games
    dựa trên industry benchmarks (methodology.md §6).

    Dùng gacha revenue làm base → estimate DAU → calculate ARPU/ARPDAU.
    """
    import random
    random.seed(42)  # reproducible

    # Genre benchmarks (from methodology.md §6)
    BENCHMARKS = {
        "RPG": {"d1": 0.45, "d7": 0.20, "d30": 0.10, "arpu": 3.0, "iap": 0.08, "crash": 0.5},
        "Action": {"d1": 0.30, "d7": 0.12, "d30": 0.05, "arpu": 0.8, "iap": 0.04, "crash": 0.8},
        "Casual": {"d1": 0.38, "d7": 0.14, "d30": 0.06, "arpu": 0.3, "iap": 0.03, "crash": 0.3},
        "default": {"d1": 0.35, "d7": 0.15, "d30": 0.07, "arpu": 1.5, "iap": 0.05, "crash": 0.5},
    }

    # Get top 15 gacha games by revenue
    with get_connection() as conn:
        games = conn.execute("""
            SELECT g.name, AVG(r.revenue_usd) as avg_rev, g.publisher
            FROM fact_gacha_revenue r
            JOIN dim_gacha_game g ON r.game_id = g.game_id
            WHERE g.publisher IS NOT NULL AND g.publisher != ''
            GROUP BY g.game_id ORDER BY avg_rev DESC LIMIT 15
        """).fetchall()

    if not games:
        logger.warning("No gacha games to simulate KPIs from")
        return 0

    rows = []
    # Simulate 30 days of KPI data
    from datetime import datetime, timedelta
    base_date = datetime(2026, 6, 1)

    for game in games:
        name = game["name"]
        avg_rev = game["avg_rev"]
        publisher = game["publisher"]

        # Estimate DAU from revenue: DAU ≈ monthly_revenue / (ARPU * 30)
        genre_key = "RPG"  # most gacha are RPG
        bench = BENCHMARKS.get(genre_key, BENCHMARKS["default"])
        estimated_dau = int(avg_rev / (bench["arpu"] * 30))

        for day_offset in range(30):
            snap_date = (base_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            # Add random variance ±15%
            variance = random.uniform(0.85, 1.15)
            dau = int(estimated_dau * variance)
            mau = int(dau * random.uniform(4.5, 5.5))  # MAU ≈ 5x DAU

            arpdau = round(bench["arpu"] / 30 * variance, 4)  # daily ARPU
            arpu = round(bench["arpu"] * variance, 2)

            d1 = round(bench["d1"] * variance, 3)
            d7 = round(bench["d7"] * variance, 3)
            d30 = round(bench["d30"] * variance, 3)
            iap = round(bench["iap"] * variance, 4)
            crash = round(bench["crash"] * random.uniform(0.8, 1.5), 2)

            rows.append({
                "game_name": name, "snapshot_date": snap_date,
                "genre": genre_key, "dau": dau, "mau": mau,
                "arpdau": arpdau, "arpu": arpu,
                "d1_retention": d1, "d7_retention": d7, "d30_retention": d30,
                "iap_conversion_pct": iap, "crash_rate_pct": crash,
            })

    df = pd.DataFrame(rows)
    with get_connection() as conn:
        conn.execute("DELETE FROM sample_daily_kpis")
        df.to_sql("sample_daily_kpis", conn, if_exists="append", index=False)
    logger.info(f"✓ Simulated KPIs: {len(df)} rows ({len(games)} games × 30 days)")
    return len(df)


def simulate_ua_campaigns():
    """
    Simulate UA campaign data (CPI/CTR/CVR/spend/installs/ROAS) cho top gacha games.

    Logic:
    - Spend = ước tính từ revenue (publisher thường re-invest 20-30% revenue vào UA)
    - CPI = benchmark theo region (methodology.md §6)
    - CTR = 1-3% (industry avg cho mobile game ads)
    - CVR = 15-30% (industry avg click → install)
    - Installs = Spend / CPI
    - Impressions = Clicks / CTR
    - ROAS = ARPU × D30_retention_lifespan / CPI
    """
    import random
    random.seed(123)

    REGIONS = {
        "VN": {"cpi_range": (0.30, 1.50), "ctr_range": (0.015, 0.035), "cvr_range": (0.20, 0.35)},
        "US": {"cpi_range": (3.0, 12.0), "ctr_range": (0.008, 0.020), "cvr_range": (0.12, 0.25)},
        "JP": {"cpi_range": (5.0, 20.0), "ctr_range": (0.010, 0.025), "cvr_range": (0.10, 0.20)},
    }
    AD_NETWORKS = ["Meta (Facebook)", "TikTok", "Google Ads", "AppLovin"]

    with get_connection() as conn:
        games = conn.execute("""
            SELECT g.name, AVG(r.revenue_usd) as avg_rev
            FROM fact_gacha_revenue r
            JOIN dim_gacha_game g ON r.game_id = g.game_id
            WHERE g.publisher IS NOT NULL AND g.publisher != ''
            GROUP BY g.game_id ORDER BY avg_rev DESC LIMIT 12
        """).fetchall()

    if not games:
        logger.warning("No gacha games to simulate UA from")
        return 0

    rows = []
    from datetime import datetime, timedelta
    base_date = datetime(2026, 6, 1)

    for game in games:
        name = game["name"]
        monthly_rev = game["avg_rev"]
        daily_spend_budget = monthly_rev * 0.25 / 30

        for day_offset in range(30):
            snap_date = (base_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            for region, bench in REGIONS.items():
                spend_share = {"VN": 0.15, "US": 0.50, "JP": 0.35}.get(region, 0.33)
                spend = daily_spend_budget * spend_share * random.uniform(0.8, 1.2)
                if spend < 10:
                    continue

                cpi = random.uniform(*bench["cpi_range"])
                installs = int(spend / cpi)
                if installs < 1:
                    continue

                ctr = random.uniform(*bench["ctr_range"])
                clicks = int(installs / random.uniform(*bench["cvr_range"]))
                impressions = int(clicks / ctr)
                cvr = installs / clicks if clicks > 0 else 0

                d1 = 0.45
                lifespan = min(60, int(1 / max(0.01, 1 - d1)))
                ltv = 3.0 * lifespan / 30
                roas_d7 = round((ltv * 0.3) / cpi, 2)
                roas_d30 = round(ltv / cpi, 2)

                rows.append({
                    "game_name": name, "snapshot_date": snap_date,
                    "region": region, "ad_network": random.choice(AD_NETWORKS),
                    "impressions": impressions, "clicks": clicks,
                    "installs": installs, "spend_usd": round(spend, 2),
                    "cpi": round(cpi, 2), "ctr": round(ctr, 4),
                    "cvr": round(cvr, 4),
                    "roas_d7": roas_d7, "roas_d30": roas_d30,
                })

    df = pd.DataFrame(rows)
    with get_connection() as conn:
        conn.execute("DELETE FROM sample_ua_campaigns")
        df.to_sql("sample_ua_campaigns", conn, if_exists="append", index=False)
    logger.info(f"✓ Simulated UA campaigns: {len(df)} rows")
    return len(df)


if __name__ == "__main__":
    init_schema()
    apply_schema()
    print("=" * 50)
    print("Loading external + simulated datasets...")
    print("=" * 50)
    n1 = load_cookie_cats()
    n2 = load_vgsales()
    n3 = simulate_daily_kpis()
    n4 = simulate_ua_campaigns()
    print()
    print(f"Cookie Cats (real retention data): {n1:,} rows")
    print(f"VG Sales (historical sales):      {n2:,} rows")
    print(f"Simulated DAU/KPIs (benchmarks):  {n3:,} rows")
    print(f"Simulated UA campaigns (CPI/CTR): {n4:,} rows")
    print()
    print("Tables: sample_cookie_cats, sample_vgsales, sample_daily_kpis, sample_ua_campaigns")
    print("⚠️  Label rõ: SAMPLE/SIMULATED data, not actual company MMP data.")
