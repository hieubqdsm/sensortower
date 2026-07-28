"""
Parse gacha revenue HTML table → SQLite.

Workflow mỗi tháng 1 lần:
  1. Mở trang revenue report (vd: revenue.ennead.cc/revenue) trên browser
  2. Copy HTML table (View Source hoặc Inspect → copy <table> element)
  3. Save vào file: data/manual/gacha_<YYYY-MM>.html
  4. Chạy: python scripts/manual/parse_gacha_html.py data/manual/gacha_2026-06.html

Hoặc pipe trực tiếp:
  cat table.html | python scripts/manual/parse_gacha_html.py

HTML format (revenue.ennead.cc style):
  <table>
    <thead><tr><th>#</th><th>Trend</th><th>Game</th>
              <th>May 2026</th><th>Jun 2026</th></tr></thead>
    <tbody>
      <tr>
        <td><span>1</span></td>                          ← rank
        <td>...trend icons...</td>
        <td>...<img alt="Game Name" src="icon.png">
            ...<span>combined</span>...</td>             ← game name (alt) + scope
        <td><span>$48,975,000</span></td>                ← prev month revenue
        <td><span>$38,375,000</span></td>                ← current month revenue
      </tr>

Parser extract: rank, game_name, scope, prev_month + prev_revenue,
                current_month + current_revenue → UPSERT cả 2 tháng.
Idempotent: UNIQUE(game_id, snapshot_month) → re-parse không duplicate.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bs4 import BeautifulSoup
from loguru import logger

from config import LOG_LEVEL, ensure_dirs
from src.storage.db import get_connection, init_schema

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)


# ---- Parsing helpers -------------------------------------------------------

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Header tháng: "May 2026" / "Jun 2026" / "2026-05"
HEADER_MONTH_RE = re.compile(
    r"(?P<month>[a-zA-Z]+)\s+(?P<year>20\d{2})|(?P<year2>20\d{2})[-/](?P<month2>\d{1,2})",
    re.IGNORECASE,
)

# Revenue: "$48,975,000" / "$48.975M" / "N/A"
REVENUE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*([MBmb]?)")
SCOPE_VALUES = {"combined", "global", "cn", "jp", "kr", "tw", "na", "eu", "ww"}


def parse_month(text: str) -> str | None:
    """Parse 'May 2026' / '2026-05' → '2026-05'. Return None if no month found."""
    if not text:
        return None
    m = HEADER_MONTH_RE.search(text)
    if not m:
        return None
    if m.group("month"):
        month_lower = m.group("month").lower()
        if month_lower not in MONTH_NAMES:
            return None
        return f"{int(m.group('year')):04d}-{MONTH_NAMES[month_lower]:02d}"
    # ISO format
    return f"{int(m.group('year2')):04d}-{int(m.group('month2')):02d}"


def parse_revenue(text: str) -> float | None:
    """Parse '$48,975,000' / '$48.975M' / 'N/A' → float USD."""
    if not text:
        return None
    s = text.strip()
    if s.upper() == "N/A" or not s:
        return None
    m = REVENUE_RE.search(s)
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    suffix = m.group(2).upper()
    if suffix == "M":
        val *= 1_000_000
    elif suffix == "B":
        val *= 1_000_000_000
    return val


def slugify(name: str) -> str:
    """Game name → URL-friendly slug: 'Love and Deepspace' → 'love-and-deepspace'."""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)  # remove non-word chars except space/hyphen
    s = re.sub(r"[\s_-]+", "-", s)  # collapse whitespace/hyphens
    return s.strip("-")


# ---- HTML table parser -----------------------------------------------------

def parse_html_table(html: str) -> dict:
    """
    Parse HTML table → {months: [prev, current], rows: [...]}.

    Returns dict:
      months: list of 'YYYY-MM' (2 values: prev_month, current_month)
      rows: list of {rank, game, scope, icon_url, revenues: [prev, current]}
    """
    soup = BeautifulSoup(html, "lxml")

    # Find the revenue table. Prefer <table>, fallback to first table in body.
    table = soup.find("table")
    if not table:
        # Maybe the pasted HTML is just <tr> rows (no <table> wrapper)
        tbody = soup.find("tbody") or soup
        if tbody.find("tr"):
            table = soup.new_tag("table")
            table.append(tbody.extract() if hasattr(tbody, "extract") else tbody)
        else:
            raise ValueError("Không tìm thấy <table> trong HTML")

    # Parse header để lấy 2 cột tháng
    thead = table.find("thead")
    month_cols: list[str] = []  # 'YYYY-MM' cho mỗi cột revenue
    if thead:
        header_cells = thead.find_all("th")
        for th in header_cells:
            text = th.get_text(" ", strip=True)
            month_iso = parse_month(text)
            if month_iso:
                month_cols.append(month_iso)
    # Fallback: scrape tháng từ first row's revenue cells (header đôi khi thiếu)
    if len(month_cols) < 2:
        logger.warning(
            f"Header chỉ có {len(month_cols)} tháng — cần ít nhất 2 (prev + current)"
        )

    # Parse body rows
    tbody = table.find("tbody") or table
    data_rows = tbody.find_all("tr", recursive=False)
    # Filter: skip empty/hidden rows (class="opacity-0 h-0")
    data_rows = [
        r for r in data_rows
        if "opacity-0" not in (r.get("class") or []) and r.find("td")
    ]

    parsed_rows = []
    for tr in data_rows:
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 4:  # need rank + game + at least 2 revenue
            continue

        # Cell 0: rank (<span>1</span>)
        rank_text = cells[0].get_text(strip=True)
        try:
            rank = int(re.search(r"\d+", rank_text).group())
        except (AttributeError, ValueError):
            continue

        # Cell 2: game (icon <img alt="Name"> + scope <span>combined</span>)
        # Cell index 1 = trend (skip). Cell 2 = game.
        game_cell = cells[2]
        game_name = None
        icon_url = None
        # Try <img alt="Game Name"> first (most reliable)
        img = game_cell.find("img")
        if img:
            game_name = (img.get("alt") or "").strip()
            icon_url = img.get("src")
        # Fallback: <button title="Game Name"> or <span class="truncate">
        if not game_name:
            btn = game_cell.find("button", attrs={"title": True})
            if btn:
                game_name = btn.get("title", "").strip()
        if not game_name:
            trunc = game_cell.find(class_="truncate")
            if trunc:
                game_name = trunc.get_text(strip=True)
        if not game_name:
            continue

        # Scope: <span class="uppercase">combined|cn|global</span>
        scope = "combined"  # default
        for span in game_cell.find_all("span"):
            txt = span.get_text(strip=True).lower()
            if txt in SCOPE_VALUES:
                scope = txt
                break

        # Revenue cells: last 2 cells (prev + current month)
        # Cells may have colored background (green/red) — we just read text
        rev_cells = cells[-len(month_cols):] if month_cols else cells[-2:]
        revenues = []
        for rc in rev_cells:
            rev_text = rc.get_text(strip=True)
            revenues.append(parse_revenue(rev_text))

        parsed_rows.append({
            "rank": rank,
            "game": game_name,
            "scope": scope,
            "icon_url": icon_url,
            "revenues": revenues,  # [prev, current] hoặc fewer
        })

    return {
        "months": month_cols,
        "rows": parsed_rows,
    }


# ---- DB upsert -------------------------------------------------------------

def upsert_game(name: str, slug: str, icon_url: str | None) -> int:
    """UPSERT dim_gacha_game. Trả game_id. Tự set first_seen_month nếu game mới."""
    with get_connection() as conn:
        # Check existing
        existing = conn.execute(
            "SELECT game_id, first_seen_month, icon_url FROM dim_gacha_game WHERE name=?",
            (name,),
        ).fetchone()
        if existing:
            # Update icon_url nếu có mới (đôi khi host đổi URL)
            if icon_url and icon_url != existing["icon_url"]:
                conn.execute(
                    "UPDATE dim_gacha_game SET icon_url=?, updated_at=datetime('now') WHERE game_id=?",
                    (icon_url, existing["game_id"]),
                )
            return existing["game_id"]
        # Insert mới — first_seen_month sẽ set sau khi biết tháng
        cur = conn.execute(
            """
            INSERT INTO dim_gacha_game (name, slug, icon_url, first_seen_month)
            VALUES (?, ?, ?, NULL)
            """,
            (name, slug, icon_url),
        )
        return cur.lastrowid


def upsert_revenue(game_id: int, month: str, rank: int, revenue: float,
                   scope: str, source: str = "ennead") -> bool:
    """UPSERT fact_gacha_revenue. Trả True nếu insert mới (không phải update)."""
    with get_connection() as conn:
        # Check existing để phân biệt insert vs update
        existing = conn.execute(
            "SELECT 1 FROM fact_gacha_revenue WHERE game_id=? AND snapshot_month=?",
            (game_id, month),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO fact_gacha_revenue
                (game_id, snapshot_month, rank, revenue_usd, scope, source)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id, snapshot_month) DO UPDATE SET
                rank=excluded.rank,
                revenue_usd=excluded.revenue_usd,
                scope=excluded.scope,
                source=excluded.source,
                fetched_at=datetime('now')
            """,
            (game_id, month, rank, revenue, scope, source),
        )
        return existing is None


def set_first_seen_month(game_id: int, month: str) -> None:
    """Set first_seen_month nếu chưa có hoặc tháng này cũ hơn."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT first_seen_month FROM dim_gacha_game WHERE game_id=?", (game_id,)
        ).fetchone()
        if not existing:
            return
        cur = existing["first_seen_month"]
        if cur is None or month < cur:
            conn.execute(
                "UPDATE dim_gacha_game SET first_seen_month=?, updated_at=datetime('now') WHERE game_id=?",
                (month, game_id),
            )


# ---- Main ------------------------------------------------------------------

def load_html(html: str, source: str = "ennead") -> dict:
    """Parse HTML + upsert vào DB. Trả stats dict."""
    parsed = parse_html_table(html)
    months = parsed["months"]
    rows = parsed["rows"]

    if len(months) < 2:
        raise ValueError(
            f"Header thiếu tháng. Tìm thấy {len(months)} tháng, cần ít nhất 2. "
            "Đảm bảo HTML có <thead> với 2 cột 'Month Year'."
        )
    if not rows:
        raise ValueError("Không parse được row nào. Kiểm tra HTML có <tbody><tr>.")

    prev_month, cur_month = months[0], months[1]
    logger.info(
        f"Parsed: {len(rows)} rows | months: prev={prev_month}, current={cur_month}"
    )

    games_added = 0
    facts_inserted = 0
    facts_updated = 0
    rows_skipped = 0

    for r in rows:
        game_name = r["game"]
        slug = slugify(game_name)
        icon_url = r["icon_url"]
        scope = r["scope"]
        rank = r["rank"]
        revenues = r["revenues"]

        # Need at least current month revenue
        if len(revenues) < 2 or revenues[1] is None:
            rows_skipped += 1
            continue

        game_id = upsert_game(game_name, slug, icon_url)
        # Detect new game
        with get_connection() as conn:
            existed_before = conn.execute(
                "SELECT 1 FROM fact_gacha_revenue WHERE game_id=?", (game_id,)
            ).fetchone()
        if not existed_before:
            games_added += 1

        # Upsert current month (always have it)
        if upsert_revenue(game_id, cur_month, rank, revenues[1], scope, source):
            facts_inserted += 1
        else:
            facts_updated += 1
        set_first_seen_month(game_id, cur_month)

        # Upsert prev month (if available — first month of tracking won't have it)
        if revenues[0] is not None:
            if upsert_revenue(game_id, prev_month, rank, revenues[0], scope, source):
                facts_inserted += 1
            else:
                facts_updated += 1
            set_first_seen_month(game_id, prev_month)

    logger.success(
        f"DONE: {len(rows)} rows parsed ({rows_skipped} skipped) | "
        f"games_added={games_added}, facts_inserted={facts_inserted}, "
        f"facts_updated={facts_updated} | months: {prev_month}, {cur_month}"
    )
    return {
        "rows_parsed": len(rows),
        "rows_skipped": rows_skipped,
        "games_added": games_added,
        "facts_inserted": facts_inserted,
        "facts_updated": facts_updated,
        "months": [prev_month, cur_month],
    }


if __name__ == "__main__":
    ensure_dirs()
    init_schema()

    # Read HTML: arg (file) hoặc stdin
    if len(sys.argv) >= 2:
        html_path = Path(sys.argv[1]).resolve()
        if not html_path.exists():
            logger.error(f"❌ File không tồn tại: {html_path}")
            sys.exit(1)
        logger.info(f"=== PARSE GACHA HTML: {html_path.name} ===")
        html_content = html_path.read_text(encoding="utf-8")
        source_tag = html_path.stem  # vd: gacha_2026-06
    elif not sys.stdin.isatty():
        logger.info("=== PARSE GACHA HTML (stdin) ===")
        html_content = sys.stdin.read()
        source_tag = "ennead"
    else:
        logger.error(
            "Cần input: `python parse_gacha_html.py <file.html>` "
            "hoặc `cat file.html | python parse_gacha_html.py`"
        )
        sys.exit(1)

    stats = load_html(html_content, source=source_tag)
    logger.info(f"=== STATS: {stats} ===")

    # DB summary
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT g.game_id) as games,
                   COUNT(DISTINCT r.snapshot_month) as months,
                   COUNT(*) as facts,
                   ROUND(SUM(r.revenue_usd)/1e6, 1) as total_musd,
                   MIN(r.snapshot_month) as first_month,
                   MAX(r.snapshot_month) as last_month
            FROM fact_gacha_revenue r
            JOIN dim_gacha_game g ON r.game_id = g.game_id
            """,
        ).fetchone()
    if row and row["facts"] > 0:
        logger.info("=== DB SUMMARY ===")
        logger.info(f"  Range: {row['first_month']} → {row['last_month']} ({row['months']} tháng)")
        logger.info(f"  Games: {row['games']}")
        logger.info(f"  Facts: {row['facts']}")
        logger.info(f"  Total est revenue (all months): ${row['total_musd']}M")
