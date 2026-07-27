"""
News crawler — morning game news briefing.

3 nguồn (tất cả public, hợp pháp, không cần key):

  1. RSS feeds (gaming news outlets):
     The Verge, Polygon, IGN, Kotaku, Eurogamer, TouchArcade, Rock Paper Shotgun
     Parse XML, lọc theo date range

  2. Reddit (JSON endpoints, không cần OAuth cho public data):
     r/games, r/gaming, r/AndroidGaming, r/iosgaming
     Lấy top posts trong 24h qua, sort by score

  3. Steam News API (cho games đang tracking):
     GetNewsForApp — patch notes, DLC announcements

Output: insert vào fact_news, dedup theo URL.
Pipeline: scripts/run_news.py --hours 24
Dashboard: trang "📰 Daily News"
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from loguru import logger

from config import PROJECT_ROOT, RAW_DIR, STEAM_API_KEY
from src.crawlers.base import BaseCrawler
from src.storage.db import get_connection


# ---- RSS feeds: các gaming news outlets tin cậy ---------------------------
# ToS: RSS feeds được publish với mục đích syndication — hợp pháp để consume
# URLs đã verify 2026-07-27: các feed cũ đã bị bỏ/deprecate
RSS_FEEDS: list[dict[str, str]] = [
    {
        "name": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "tos": "https://www.voxmedia.com/legal/vox-media-terms-service",
    },
    {
        "name": "IGN",
        "url": "https://feeds.feedburner.com/ign/all",
        "tos": "https://corp.ign.com/terms-of-service",
    },
    {
        "name": "Eurogamer",
        "url": "https://www.eurogamer.net/feed",
        "tos": "https://www.eurogamer.net/terms-of-service",
    },
    {
        "name": "PCGamer",
        "url": "https://www.pcgamer.com/rss/",
        "tos": "https://www.pcgamer.com/terms-of-service/",
    },
    {
        "name": "Rock Paper Shotgun",
        "url": "https://www.rockpapershotgun.com/feed",
        "tos": "https://www.rockpapershotgun.com/terms-of-service",
    },
    # Bỏ: Polygon (connection drop), Kotaku (403), TouchArcade (no recent items),
    # The Verge Gaming (404) — endpoints không ổn định 2026
]

# ---- Reddit subreddits (YÊU CẦU OAuth từ 2023) ---------------------------
# Reddit đã chặn unauthenticated JSON requests (403 Blocked).
# Cần đăng ký Reddit app (free, OAuth2 client_credentials):
#   https://www.reddit.com/prefs/apps → create "script" app
#   → set REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET trong .env
# Hiện tại SKIP Reddit nếu chưa có OAuth credentials.
REDDIT_SUBREDDITS: list[str] = [
    "games",           # general gaming news (high quality)
    "gaming",          # general gaming (high volume)
    "AndroidGaming",   # mobile gaming focus
    "iosgaming",       # iOS gaming focus
    "gachagaming",     # mobile gacha (match VN market)
    "mobilegaming",    # mobile general
]

# ---- Hacker News (Y Combinator) — JSON API public miễn phí --------------
# ToS: cho phép, không cần auth, không có rate limit nghiêm ngặt
# Filter stories có "game" trong title để lấy relevant
HACKER_NEWS_BASE = "https://hacker-news.firebaseio.com/v0"


class NewsCrawler(BaseCrawler):
    """
    Crawler cho morning briefing. Kết hợp RSS + Reddit + Steam News.
    """

    def __init__(self, hours: int = 24) -> None:
        super().__init__("news")  # dùng source_name="news" cho raw dir
        self.raw_dir = RAW_DIR / "news"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.hours = hours
        self.cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
        # Reddit yêu cầu User-Agent custom (không được dùng "python-requests")
        self.session.headers.update({
            "User-Agent": "GameBI-Pipeline/0.1 (morning news digest; portfolio project)"
        })

    # ====================================================================
    # DB helpers
    # ====================================================================
    def _get_or_create_source(self, source_type: str, name: str,
                              feed_url: str | None = None,
                              tos_url: str | None = None) -> int:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dim_news_source (source_type, source_name, feed_url, tos_url)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_type, source_name) DO UPDATE SET
                    feed_url=excluded.feed_url, tos_url=excluded.tos_url
                """,
                (source_type, name, feed_url, tos_url),
            )
            row = conn.execute(
                "SELECT source_id FROM dim_news_source WHERE source_type=? AND source_name=?",
                (source_type, name),
            ).fetchone()
            return row["source_id"]

    def _match_game(self, text: str) -> int | None:
        """Match text với dim_game.name → trả về game_id nếu tìm được."""
        if not text:
            return None
        with get_connection() as conn:
            # Match đơn giản: case-insensitive substring
            rows = conn.execute(
                "SELECT game_id, name FROM dim_game WHERE LOWER(?) LIKE '%' || LOWER(name) || '%' "
                "   OR LOWER(name) LIKE '%' || LOWER(?) || '%'",
                (text, text[:80]),
            ).fetchall()
            if not rows:
                # Reverse: tìm game name trong text
                rows = conn.execute("SELECT game_id, name FROM dim_game").fetchall()
                text_lower = text.lower()
                for r in rows:
                    name_lower = (r["name"] or "").lower()
                    # Lấy 4+ ký tự đầu làm match key (tránh match "Roblox" với "Ro")
                    if len(name_lower) >= 4 and name_lower in text_lower:
                        return r["game_id"]
            else:
                return rows[0]["game_id"]
        return None

    def _detect_keywords(self, text: str) -> str:
        """Detect business-relevant keywords trong text."""
        if not text:
            return ""
        text_lower = text.lower()
        keywords = []
        # Map: (keyword_list, tag)
        keyword_map = [
            (["launch", "release", "out now", "debut"], "launch"),
            (["update", "patch", "patch notes", "hotfix", "v1.", "v2."], "update"),
            (["shutdown", "sunset", "end of service", "closing"], "shutdown"),
            (["layoff", "layoffs", "job cut", "fired", "restructuring"], "layoffs"),
            (["acquire", "acquisition", "buys", "bought by", "merger"], "acquisition"),
            (["funding", "raise", "series a", "series b", "investment"], "funding"),
            (["dlc", "expansion", "season pass"], "dlc"),
            (["mobile", "ios", "android", "app store"], "mobile"),
            (["esport", "tournament", "championship"], "esport"),
            (["review", "hands-on", "preview"], "review"),
        ]
        for kws, tag in keyword_map:
            if any(kw in text_lower for kw in kws):
                keywords.append(tag)
        return ",".join(keywords)

    def upsert_news(self, source_id: int, title: str, url: str,
                    summary: str | None, author: str | None,
                    published_at: str, score: int | None = None,
                    game_id: int | None = None, keywords: str | None = None) -> bool:
        """
        UPSERT news item. Trả True nếu inserted mới (không phải đã có).
        Dedup theo URL.
        """
        # Detect keywords tự động nếu không truyền
        if not keywords:
            full_text = f"{title} {summary or ''}"
            keywords = self._detect_keywords(full_text)

        # Match game tự động nếu không truyền
        if not game_id:
            game_id = self._match_game(f"{title} {summary or ''}")

        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO fact_news
                    (source_id, game_id, title, url, summary, author,
                     published_at, score, keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    score=excluded.score,
                    keywords=excluded.keywords
                """,
                (source_id, game_id, title, url, summary, author,
                 published_at, score, keywords),
            )
            # cur.rowcount > 0 nghĩa là có change (insert hoặc update)
            # Để phân biệt: check via last_insert_rowid vs existing
            return cur.rowcount > 0

    # ====================================================================
    # RSS: XML parsing
    # ====================================================================
    def parse_rss_date(self, date_str: str) -> datetime | None:
        """Parse các format RSS date phổ biến."""
        if not date_str:
            return None
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",    # RFC 822: "Mon, 27 Jul 2026 09:00:00 +0000"
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%dT%H:%M:%S%z",          # ISO: "2026-07-27T09:00:00+00:00"
            "%Y-%m-%dT%H:%M:%SZ",           # ISO UTC
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None

    def fetch_rss_feed(self, feed: dict[str, str]) -> int:
        """Fetch 1 RSS feed → insert news items trong cutoff range."""
        name = feed["name"]
        url = feed["url"]
        source_id = self._get_or_create_source("rss", name, feed_url=url,
                                                tos_url=feed.get("tos"))
        try:
            # RSS trả XML, không phải JSON — gọi raw session
            self._respect_rate_limit()
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            xml_text = resp.text
        except Exception as e:
            logger.warning(f"[news] RSS fetch {name} failed: {e}")
            return 0

        # Save raw XML để audit
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        today = datetime.now().strftime("%Y-%m-%d")
        raw_path = self.raw_dir / today / f"rss_{safe_name}.xml"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(xml_text, encoding="utf-8")

        # Parse XML
        inserted = 0
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning(f"[news] RSS parse {name} failed: {e}")
            return 0

        # RSS 2.0: <item> ; Atom: <entry>
        items = root.findall(".//item") or root.findall(".//entry")
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            # Atom: link có href attribute
            if not link:
                link_el = item.find("link")
                if link_el is not None:
                    link = link_el.get("href", "")
            summary = (item.findtext("description") or item.findtext("summary") or "").strip()
            # Strip HTML tags đơn giản
            summary = re.sub(r"<[^>]+>", " ", summary)[:500]
            pub_date = (item.findtext("pubDate") or item.findtext("published") or "").strip()
            author = (item.findtext("author") or item.findtext("dc:creator") or "").strip()

            if not title or not link:
                continue

            dt = self.parse_rss_date(pub_date)
            if dt is None:
                continue  # skip items không có date parse được
            if dt < self.cutoff_dt:
                continue  # ngoài range 24h

            ok = self.upsert_news(
                source_id=source_id, title=title, url=link,
                summary=summary, author=author,
                published_at=dt.isoformat(), score=None,
            )
            if ok:
                inserted += 1

        logger.info(f"[news] RSS {name}: {inserted} new items (last {self.hours}h)")
        return inserted

    # ====================================================================
    # Hacker News (Firebase public API) — no auth, no rate limit issues
    # ====================================================================
    def fetch_hacker_news(self, max_stories: int = 100) -> int:
        """
        Lấy top stories từ HN, filter stories có keyword 'game' trong title.
        HN không chuyên game nhưng đôi khi có insight industry (funding, layoff, M&A).
        """
        source_id = self._get_or_create_source(
            "hackernews", "Hacker News",
            feed_url="https://hacker-news.firebaseio.com/v0",
            tos_url="https://news.ycombinator.com/tos",
        )

        try:
            top_ids = self.get_json(f"{HACKER_NEWS_BASE}/topstories.json")
        except Exception as e:
            logger.warning(f"[news] HN topstories failed: {e}")
            return 0

        # Lấy top N stories
        top_ids = (top_ids or [])[:max_stories]
        inserted = 0
        for story_id in top_ids:
            try:
                story = self.get_json(f"{HACKER_NEWS_BASE}/item/{story_id}.json")
            except Exception:
                continue
            if not story or story.get("type") != "story":
                continue

            title = (story.get("title") or "").strip()
            url_full = (story.get("url") or "").strip()
            if not title or not url_full:
                continue

            # Filter game-related
            title_lower = title.lower()
            game_keywords = ["game", "gaming", "steam", "playstation", "xbox",
                             "nintendo", "esport", "twitch", "roblox", "minecraft"]
            if not any(kw in title_lower for kw in game_keywords):
                continue

            # Time filter
            ts = story.get("time")
            try:
                dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            except (ValueError, TypeError):
                continue
            if dt < self.cutoff_dt:
                continue

            score = story.get("score", 0)
            author = story.get("by", "")

            ok = self.upsert_news(
                source_id=source_id, title=title, url=url_full,
                summary=None, author=author,
                published_at=dt.isoformat(), score=score,
            )
            if ok:
                inserted += 1

        logger.info(f"[news] Hacker News: {inserted} game-related stories (last {self.hours}h)")
        return inserted

    # ====================================================================
    # Reddit: YÊU CẦU OAuth (Reddit chặn unauthenticated từ 2023)
    # ====================================================================
    def fetch_reddit_subreddit(self, subreddit: str) -> int:
        """Fetch top posts từ subreddit trong range hours."""
        # Dùng /top endpoint với t=day (hoặc hour nếu hours<=1)
        if self.hours <= 1:
            time_filter = "hour"
        elif self.hours <= 24:
            time_filter = "day"
        elif self.hours <= 24 * 7:
            time_filter = "week"
        else:
            time_filter = "month"

        url = f"https://www.reddit.com/r/{subreddit}/top.json?t={time_filter}&limit=50"
        source_id = self._get_or_create_source(
            "reddit", f"r/{subreddit}",
            feed_url=f"https://reddit.com/r/{subreddit}",
            tos_url="https://www.redditinc.com/policies/content-policy",
        )

        try:
            payload = self.get_json(url)
        except Exception as e:
            logger.warning(f"[news] Reddit r/{subreddit} failed: {e}")
            return 0

        children = ((payload.get("data") or {}).get("children") or [])
        inserted = 0

        for child in children:
            d = child.get("data") or {}
            title = (d.get("title") or "").strip()
            permalink = d.get("permalink")
            if not title or not permalink:
                continue
            url_full = f"https://www.reddit.com{permalink}"
            score = d.get("score", 0)
            author = d.get("author", "")
            # Reddit timestamp là unix seconds
            created_utc = d.get("created_utc")
            if not created_utc:
                continue
            try:
                dt = datetime.fromtimestamp(created_utc, tz=timezone.utc)
            except (ValueError, OSError):
                continue
            if dt < self.cutoff_dt:
                continue

            # Selftext làm summary nếu có (và không quá dài)
            selftext = (d.get("selftext") or "").strip()
            summary = re.sub(r"\s+", " ", selftext)[:500] if selftext else None

            ok = self.upsert_news(
                source_id=source_id, title=title, url=url_full,
                summary=summary, author=author,
                published_at=dt.isoformat(), score=score,
            )
            if ok:
                inserted += 1

        logger.info(f"[news] Reddit r/{subreddit}: {inserted} new posts (last {self.hours}h)")
        return inserted

    # ====================================================================
    # Steam News API: GetNewsForApp cho games đang track
    # ====================================================================
    def fetch_steam_news(self) -> int:
        """Fetch news cho các game Steam đang có trong DB."""
        if not STEAM_API_KEY:
            logger.info("[news] Steam news skipped (no STEAM_API_KEY)")
            return 0

        with get_connection() as conn:
            steam_games = conn.execute(
                "SELECT game_id, source_app_id, name FROM dim_game WHERE source='steam'"
            ).fetchall()

        if not steam_games:
            logger.info("[news] Steam news skipped (no Steam games in DB)")
            return 0

        source_id = self._get_or_create_source(
            "steam_news", "Steam",
            feed_url="https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/",
            tos_url="https://steamcommunity.com/dev/apiterms",
        )

        url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
        inserted = 0
        for g in steam_games:
            appid = g["source_app_id"]
            params = {
                "appid": appid,
                "count": 10,
                "maxlength": 500,
                "feeds": "steam_community_announcements",
            }
            try:
                payload = self.get_json(url, params=params)
            except Exception as e:
                logger.warning(f"[news] Steam news appid={appid} failed: {e}")
                continue

            items = ((payload.get("appnews") or {}).get("newsitems") or [])
            for item in items:
                title = (item.get("title") or "").strip()
                url_full = (item.get("url") or "").strip()
                if not title or not url_full:
                    continue
                # Steam date là unix seconds
                dt_ts = item.get("date")
                try:
                    dt = datetime.fromtimestamp(int(dt_ts), tz=timezone.utc)
                except (ValueError, OSError, TypeError):
                    continue
                if dt < self.cutoff_dt:
                    continue

                summary = (item.get("contents") or "").strip()[:500]
                author = item.get("author") or item.get("feedlabel")

                ok = self.upsert_news(
                    source_id=source_id, title=title, url=url_full,
                    summary=summary, author=author,
                    published_at=dt.isoformat(),
                    score=None, game_id=g["game_id"],
                )
                if ok:
                    inserted += 1

        logger.info(f"[news] Steam News: {inserted} new items ({len(steam_games)} games)")
        return inserted

    # ====================================================================
    # MAIN ENTRY
    # ====================================================================
    def run(self, max_items: int = 0) -> dict[str, int]:
        """Chạy cả 3 nguồn. max_items không dùng (lấy tất cả trong range hours)."""
        logger.info(f"[news] starting crawl: hours={self.hours}")
        logger.info(f"[news] cutoff: {self.cutoff_dt.isoformat()}")

        rss_total = 0
        for feed in RSS_FEEDS:
            rss_total += self.fetch_rss_feed(feed)
            time.sleep(1)  # polite delay giữa RSS sources

        # Reddit: skip vì 403 (cần OAuth, chưa config)
        reddit_total = 0
        import os
        has_reddit_auth = bool(os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET"))
        if has_reddit_auth:
            for sub in REDDIT_SUBREDDITS:
                reddit_total += self.fetch_reddit_subreddit(sub)
                time.sleep(2)
        else:
            logger.info("[news] Reddit skipped (no OAuth credentials — see comments in news_crawler.py)")

        # Hacker News (luôn chạy, ổn định)
        hn_total = self.fetch_hacker_news()

        steam_total = self.fetch_steam_news()

        # Final count from DB (dedupped)
        with get_connection() as conn:
            total = conn.execute(
                """
                SELECT COUNT(*) FROM fact_news
                WHERE published_at >= ?
                """,
                (self.cutoff_dt.isoformat(),),
            ).fetchone()[0]

        logger.success(
            f"[news] DONE: rss={rss_total}, reddit={reddit_total}, "
            f"hackernews={hn_total}, steam={steam_total} | "
            f"total unique in DB (last {self.hours}h): {total}"
        )
        return {
            "rss_inserted": rss_total,
            "reddit_inserted": reddit_total,
            "hackernews_inserted": hn_total,
            "steam_inserted": steam_total,
            "total_in_range": total,
        }
