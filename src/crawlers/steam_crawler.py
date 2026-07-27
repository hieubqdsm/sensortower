"""
Steam Web API crawler.

Lấy top game Steam theo player count, sau đó fetch metadata chi tiết.

Endpoints (toàn bộ public theo Steam ToS):
  - https://api.steampowered.com/ISteamChartsService/GetTopPlayedGames/v1/
        → top games theo CCU (cần API key)
  - https://store.steampowered.com/api/appdetails?appids=<id>
        → metadata (name, price, genre, dev, publisher, release_date)
  - https://store.steampowered.com/appreviews/<id>?json=1
        → review counts (positive/negative)
  - https://api.steampowered.com/ISteamChartsService/GetGamesByApp/v1/?appid=<id>
        → CCU snapshot

Tất cả response được save raw vào data/raw/steam/<date>/ rồi upsert vào DB.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger

from config import PROJECT_ROOT, STEAM_API_KEY
from src.crawlers.base import BaseCrawler
from src.storage.db import get_connection


class SteamCrawler(BaseCrawler):
    def __init__(self) -> None:
        super().__init__("steam")
        if not STEAM_API_KEY:
            raise RuntimeError(
                "STEAM_API_KEY missing. Get one at "
                "https://steamcommunity.com/dev/apikey"
            )
        self.api_key = STEAM_API_KEY
        self.charts_url = "https://api.steampowered.com/ISteamChartsService/GetTopPlayedGames/v1/"
        self.appdetails_url = "https://store.steampowered.com/api/appdetails"
        self.reviews_url = "https://store.steampowered.com/appreviews/{appid}"

    # ---- Lấy top games theo CCU -----------------------------------------
    def fetch_top_appids(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Trả list các dict: [{"appid": 730, "rank": 1, "peak_indep": 1.2M}, ...]
        """
        params = {"key": self.api_key}
        try:
            payload = self.get_json(self.charts_url, params=params)
        except Exception as e:
            logger.error(f"[steam] GetTopPlayedGames failed: {e}")
            # Fallback: dùng endpoint public GetMostPlayedGames
            payload = self.get_json(
                "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/",
                params=params,
            )

        rows = payload.get("response", {}).get("ranks", []) or []
        top = rows[:limit]
        logger.info(f"[steam] fetched {len(top)} top appids (limit={limit})")
        return top

    # ---- Lấy chi tiết 1 game --------------------------------------------
    def fetch_app_details(self, appid: int) -> dict[str, Any] | None:
        """Lấy metadata: name, price, genre, dev, publisher, release date."""
        try:
            payload = self.get_json(self.appdetails_url, params={"appids": appid})
        except Exception as e:
            logger.warning(f"[steam] appdetails {appid} failed: {e}")
            return None
        data = payload.get(str(appid), {})
        if not data.get("success"):
            return None
        return data.get("data")

    # ---- Lấy review counts ----------------------------------------------
    def fetch_review_summary(self, appid: int) -> dict[str, int]:
        """Trả {"positive": N, "negative": M}."""
        url = self.reviews_url.format(appid=appid)
        params = {
            "json": 1,
            "purchase_type": "all",
            "language": "all",
            "num_per_page": 0,
        }
        try:
            payload = self.get_json(url, params=params)
        except Exception as e:
            logger.warning(f"[steam] reviews {appid} failed: {e}")
            return {"positive": 0, "negative": 0}
        q = payload.get("query_summary", {})
        return {
            "positive": q.get("total_positive", 0),
            "negative": q.get("total_negative", 0),
        }

    # ---- Lấy CCU realtime của 1 game ------------------------------------
    def fetch_current_ccu(self, appid: int) -> int:
        """Peak concurrent users hiện tại."""
        url = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
        try:
            payload = self.get_json(url, params={"appid": appid})
        except Exception as e:
            logger.warning(f"[steam] CCU {appid} failed: {e}")
            return 0
        return payload.get("response", {}).get("player_count", 0)

    # ---- Persist fact ----------------------------------------------------
    def upsert_playercount_fact(
        self, game_id: int, snapshot_date: str,
        peak_ccu: int, positive: int, negative: int,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO fact_steam_playercounts
                    (game_id, snapshot_date, peak_ccu,
                     positive_reviews, negative_reviews)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(game_id, snapshot_date) DO UPDATE SET
                    peak_ccu=excluded.peak_ccu,
                    positive_reviews=excluded.positive_reviews,
                    negative_reviews=excluded.negative_reviews
                """,
                (game_id, snapshot_date, peak_ccu, positive, negative),
            )

    # ---- Main entry ------------------------------------------------------
    def run(self, max_items: int = 100) -> dict[str, int]:
        today = date.today().isoformat()
        logger.info(f"[steam] starting crawl, max_items={max_items}, date={today}")

        top = self.fetch_top_appids(limit=max_items)
        if not top:
            logger.warning("[steam] no top games returned — abort")
            return {"games_crawled": 0, "facts_inserted": 0}

        games_ok = 0
        facts_ok = 0

        for row in top:
            appid = row.get("appid")
            if not appid:
                continue

            # 1. Metadata
            details = self.fetch_app_details(appid)
            # Save raw luôn (dù details có thể None)
            raw_path = self.save_raw(
                f"appdetails_{appid}", details or {"appid": appid, "success": False}, today
            )

            if details:
                price = (details.get("price_overview") or {}).get("final") or 0
                price_usd = price / 100.0 if price else 0.0  # price tính bằng cents
                genres = [g.get("description", "") for g in details.get("genres", []) if g.get("description")]
                genre = genres[0] if genres else None
                release_date = (details.get("release_date") or {}).get("date")
                devs = details.get("developers") or []
                pubs = details.get("publishers") or []

                game_id = self.upsert_game(
                    source_app_id=str(appid),
                    name=details.get("name", f"SteamApp_{appid}"),
                    genre=genre,
                    platform="pc",
                    release_date=release_date,
                    price_usd=price_usd,
                    publisher_name=pubs[0] if pubs else None,
                    developer_name=devs[0] if devs else None,
                    description=(details.get("short_description") or "")[:500],
                    raw_payload_path=str(raw_path.relative_to(PROJECT_ROOT)),
                )
                games_ok += 1
            else:
                # Fallback: vẫn insert row tối thiểu để track CCU
                game_id = self.upsert_game(
                    source_app_id=str(appid),
                    name=f"SteamApp_{appid}",
                    platform="pc",
                    raw_payload_path=str(raw_path),
                )

            # 2. Reviews
            reviews = self.fetch_review_summary(appid)
            self.save_raw(f"reviews_{appid}", reviews, today)

            # 3. CCU (peak_indep từ top charts hoặc gọi GetNumberOfCurrentPlayers)
            peak_ccu = row.get("peak_indep") or row.get("concurrent") or 0
            if not peak_ccu:
                peak_ccu = self.fetch_current_ccu(appid)

            # 4. Persist fact
            self.upsert_playercount_fact(
                game_id=game_id,
                snapshot_date=today,
                peak_ccu=int(peak_ccu),
                positive=reviews["positive"],
                negative=reviews["negative"],
            )
            facts_ok += 1

        logger.success(f"[steam] DONE: {games_ok} games, {facts_ok} facts")
        return {"games_crawled": games_ok, "facts_inserted": facts_ok}
