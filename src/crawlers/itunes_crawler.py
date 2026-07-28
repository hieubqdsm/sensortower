"""
iTunes crawler — public Apple APIs (không cần key).

Hai nguồn kết hợp:

  1. iTunes Search API (PRIMARY cho games catalog):
       https://itunes.apple.com/search?term=...&primaryGenreId=6014&entity=software
     → Trả games chính xác (genre ID 6014 = Games), đầy đủ metadata
     → Là nguồn chính để populate dim_game với game thật

  2. Apple Marketing Tools RSS (CHO RANKINGS):
       https://rss.marketingtools.apple.com/api/v2/<country>/apps/<type>/<count>/apps.json
     Types: top-free, top-paid (top-grossing đã bị Apple bỏ)
     → Trả overall top apps (KHÔNG filter games — Apple RSS không hỗ trợ)
     → Dùng để track ranking changes (market overview)

Trade-off đã biết:
  - RSS không filter games → ranking data chứa cả non-game apps
  - Search API không trả ranking chính thức, chỉ "popular results" theo relevance
  → Pipeline lưu cả 2, Power BI sẽ filter games-only ở query time
    (WHERE g.genre = 'Games' OR g.source_app_id IN (select from search results))

JD quan tâm market VN — pipeline mặc định crawl cả US + VN để so sánh.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger

from config import PROJECT_ROOT
from src.crawlers.base import BaseCrawler
from src.storage.db import get_connection


# Storefront codes (Apple Marketing Tools RSS dùng ISO 2-letter country)
DEFAULT_COUNTRIES = ["us", "vn"]

# Chart types: mỗi (country, chart_type) cho top N apps
# Note: Apple RSS chỉ support "top-free" và "top-paid". "top-grossing" đã bị bỏ.
DEFAULT_CHARTS = ["top-free", "top-paid"]

# Apple Games category ID (chuẩn iTunes)
GAMES_PRIMARY_GENRE_ID = 6014

# Search term dùng để discovery games qua Search API
# "" trả popular/trending, "game" broaden kết quả
GAMES_SEARCH_TERM = "game"


class ITunesCrawler(BaseCrawler):
    def __init__(
        self,
        countries: list[str] | None = None,
        chart_types: list[str] | None = None,
    ) -> None:
        super().__init__("itunes")
        self.countries = countries or DEFAULT_COUNTRIES
        self.chart_types = chart_types or DEFAULT_CHARTS
        self.rss_url = "https://rss.applemarketingtools.com/api/v2/{country}/apps/{chart}/{count}/apps.json"
        self.search_url = "https://itunes.apple.com/search"
        self.lookup_url = "https://itunes.apple.com/lookup"

    # ====================================================================
    # METHOD 1: iTunes Search API — top games (genre-filtered, chính xác)
    # ====================================================================
    def fetch_top_games(self, country: str, limit: int = 100) -> list[dict[str, Any]]:
        """
        Lấy top games của 1 country qua Search API với primaryGenreId=6014.
        Trả list app payloads (đã có đầy đủ metadata, không cần lookup thêm).
        """
        params = {
            "term": GAMES_SEARCH_TERM,
            "country": country,
            "media": "software",
            "entity": "software",
            "primaryGenreId": GAMES_PRIMARY_GENRE_ID,
            "limit": limit,
        }
        try:
            payload = self.get_json(self.search_url, params=params)
        except Exception as e:
            logger.error(f"[itunes] search games {country} failed: {e}")
            return []
        results = payload.get("results", []) or []
        logger.info(f"[itunes] {country}/search-games: {len(results)} games")
        return results

    def upsert_game_from_search(self, game: dict[str, Any], country: str, today: str) -> int | None:
        """Upsert 1 game (từ Search API) vào dim_game. Trả game_id."""
        app_id = str(game.get("trackId"))
        if not app_id:
            return None
        raw_path = self.save_raw(f"game_{country}_{app_id}", game, today)
        genres = game.get("genres") or []
        # Pick sub-genre (skip generic "Games"/"Entertainment" parents) for detail
        primary_genre = (
            game.get("primaryGenreName")
            or next((g for g in genres if g and g not in ("Games", "Entertainment")), None)
            or (genres[0] if genres else "Games")
        )
        price = game.get("price") or 0.0

        return self.upsert_game(
            source_app_id=app_id,
            name=game.get("trackName") or f"App_{app_id}",
            genre=primary_genre,
            platform="ios",
            release_date=(game.get("releaseDate") or "")[:10] or None,
            price_usd=float(price),
            publisher_name=game.get("artistName"),
            developer_name=game.get("artistName"),
            description=(game.get("description") or "")[:500],
            raw_payload_path=str(raw_path.relative_to(PROJECT_ROOT)),
        )

    # ====================================================================
    # METHOD 2: RSS top charts (overall, dùng cho rankings)
    # ====================================================================
    def fetch_top_chart(self, country: str, chart: str, count: int) -> list[dict[str, Any]]:
        """
        Lấy top apps theo country + chart (overall, không filter games).
        Apple RSS không hỗ trợ category filter.
        """
        url = self.rss_url.format(country=country, chart=chart, count=count)
        try:
            payload = self.get_json(url)
        except Exception as e:
            logger.error(f"[itunes] RSS {country}/{chart} failed: {e}")
            return []
        feed = payload.get("feed", {})
        results = feed.get("results", []) or []
        logger.info(f"[itunes] {country}/{chart}: fetched {len(results)} apps (overall)")
        return results

    def lookup_app(self, app_id: str) -> dict[str, Any] | None:
        """Lấy metadata đầy đủ cho 1 app."""
        try:
            payload = self.get_json(self.lookup_url, params={"id": app_id})
        except Exception as e:
            logger.warning(f"[itunes] lookup {app_id} failed: {e}")
            return None
        results = payload.get("results", []) or []
        return results[0] if results else None

    def upsert_ranking_fact(
        self,
        game_id: int,
        snapshot_date: str,
        country: str,
        chart_name: str,
        rank: int,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO fact_itunes_rankings
                    (game_id, snapshot_date, country, chart_name, rank)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(game_id, snapshot_date, country, chart_name) DO UPDATE SET
                    rank=excluded.rank
                """,
                (game_id, snapshot_date, country.upper(), chart_name, rank),
            )

    # ====================================================================
    # MAIN ENTRY
    # ====================================================================
    def run(self, max_items: int = 100) -> dict[str, int]:
        today = date.today().isoformat()
        logger.info(
            f"[itunes] starting crawl: countries={self.countries}, "
            f"charts={self.chart_types}, target={max_items}"
        )

        # ---- Pass 1: Search API → populate dim_game + ranking facts --------
        # Search API trả games theo popularity order (genre-filtered = 6014/Games).
        # Dùng position trong result làm RANK (1-based) → reliable, không cần RSS.
        games_seen: set[str] = set()
        rankings_ok = 0
        for country in self.countries:
            games = self.fetch_top_games(country, limit=max_items)
            for rank_idx, g in enumerate(games, start=1):
                app_id = str(g.get("trackId"))
                if not app_id or app_id in games_seen:
                    continue
                gid = self.upsert_game_from_search(g, country, today)
                if gid:
                    games_seen.add(app_id)
                    # Insert ranking fact (rank = position trong Search results)
                    # Chart name = "top-games" vì Search đã filter genre=Games
                    self.upsert_ranking_fact(
                        game_id=gid,
                        snapshot_date=today,
                        country=country.upper(),
                        chart_name="top-games",
                        rank=rank_idx,
                    )
                    rankings_ok += 1
            logger.info(f"[itunes] {country}: {len(games_seen)} unique games so far")

        # ---- Pass 2 (optional): RSS → lưu raw chart để audit (không insert ranking) ----
        # Lý do skip RSS cho ranking: RSS chỉ có overall top apps (không filter games),
        # và phải lookup từng app → chậm + hầu hết non-game. Search API đã đủ.
        for country in self.countries:
            for chart in self.chart_types:
                try:
                    apps = self.fetch_top_chart(country, chart, count=max_items)
                    self.save_raw(f"chart_{country}_{chart}", apps, today)
                except Exception as e:
                    logger.warning(f"[itunes] RSS {country}/{chart} save failed: {e}")

        logger.success(
            f"[itunes] DONE: {len(games_seen)} unique games, {rankings_ok} rankings"
        )
        return {
            "games_crawled": len(games_seen),
            "rankings_inserted": rankings_ok,
        }

    def _get_game_id(self, app_id: str) -> int | None:
        """Lookup surrogate game_id từ dim_game."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT game_id FROM dim_game WHERE source=? AND source_app_id=?",
                ("itunes", app_id),
            ).fetchone()
            return row["game_id"] if row else None
