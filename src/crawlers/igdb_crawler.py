"""
IGDB crawler — game catalog enrichment via Twitch OAuth.

IGDB là DB game cross-platform do Twitch vận hành. Dùng để:
  - Enrich dim_game với genres, platforms, release dates chuẩn
  - Cross-reference Steam/iTunes games để có catalog metadata thống nhất

Auth flow:
  POST https://id.twitch.tv/oauth2/token
       ?client_id=...&client_secret=...&grant_type=client_credentials
  → access_token (hết hạn ~60 ngày, refresh mỗi lần chạy)

API query (POST body dạng Apache Caldera-style):
  POST https://api.igdb.com/v4/games
  Headers: Client-ID, Authorization: Bearer <token>
  Body: fields name,genres.name,platforms.name,first_release_date,...;
        where rating > 80; sort rating desc; limit 100;

Note: IGDB free tier giới hạn 4 req/s concurrent, 10k req/tháng.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger

from config import PROJECT_ROOT, TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET
from src.crawlers.base import BaseCrawler
from src.storage.db import get_connection


# Sort options: top-rated hoặc hyped
DEFAULT_QUERY_BODY = (
    "fields id,name,genres.name,platforms.name,first_release_date,"
    "rating,rating_count,aggregated_rating,summary,involved_companies.company.name,"
    "involved_companies.publisher,involved_companies.developer;"
    " where rating != null & first_release_date > 1577836800;"  # sau 2020-01-01
    " sort rating desc;"
    " limit {limit};"
)


class IGDBCrawler(BaseCrawler):
    def __init__(self) -> None:
        super().__init__("igdb")
        if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
            raise RuntimeError(
                "TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET missing. "
                "Register at https://dev.twitch.tv/console"
            )
        self.client_id = TWITCH_CLIENT_ID
        self.client_secret = TWITCH_CLIENT_SECRET
        self.token_url = "https://id.twitch.tv/oauth2/token"
        self.games_url = "https://api.igdb.com/v4/games"
        self._access_token: str | None = None

    # ---- OAuth -----------------------------------------------------------
    def get_access_token(self) -> str:
        """
        Lấy access_token qua client_credentials flow.
        IGDB khuyến nghị cache token — mình store trong instance, refresh mỗi run.
        """
        if self._access_token:
            return self._access_token
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        try:
            payload = self.post_json(self.token_url, data=params)
        except Exception as e:
            logger.error(f"[igdb] token fetch failed: {e}")
            raise
        self._access_token = payload.get("access_token")
        if not self._access_token:
            raise RuntimeError(f"[igdb] no access_token in response: {payload}")
        logger.info("[igdb] access token acquired")
        return self._access_token

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.get_access_token()}",
            "Accept": "application/json",
        }

    # ---- Query games -----------------------------------------------------
    def fetch_top_games(self, limit: int = 100) -> list[dict[str, Any]]:
        """Lấy top game theo rating."""
        body = DEFAULT_QUERY_BODY.format(limit=limit)
        headers = self._auth_headers()
        try:
            payload = self.post_json(self.games_url, data=body, headers=headers)
        except Exception as e:
            logger.error(f"[igdb] query failed: {e}")
            return []
        # IGDB trả về list trực tiếp (không phải wrapper)
        if isinstance(payload, list):
            return payload
        logger.warning(f"[igdb] unexpected payload type: {type(payload)}")
        return []

    # ---- Persist ---------------------------------------------------------
    def upsert_game_row(self, game: dict[str, Any], raw_path_str: str) -> int:
        """UPSERT game IGDB vào dim_game."""
        game_id_igdb = str(game.get("id"))
        genres = game.get("genres") or []
        primary_genre = (genres[0] if genres and isinstance(genres[0], dict)
                         else None)
        genre_name = primary_genre.get("name") if isinstance(primary_genre, dict) else None

        # Platforms: take names
        platforms = game.get("platforms") or []
        platform_names = [
            p.get("name") for p in platforms
            if isinstance(p, dict) and p.get("name")
        ]
        platform_str = "|".join(platform_names[:3]) if platform_names else None

        # Involved companies (publishers/developers)
        involved = game.get("involved_companies") or []
        pub_name = dev_name = None
        for ic in involved:
            if not isinstance(ic, dict):
                continue
            company = ic.get("company") or {}
            cname = company.get("name") if isinstance(company, dict) else None
            if ic.get("publisher") and not pub_name:
                pub_name = cname
            if ic.get("developer") and not dev_name:
                dev_name = cname

        # Release date (unix → ISO)
        release_ts = game.get("first_release_date")
        release_iso = None
        if release_ts:
            try:
                release_iso = date.fromtimestamp(int(release_ts)).isoformat()
            except (ValueError, OSError):
                release_iso = None

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dim_game (
                    source_app_id, source, name, genre, platform,
                    release_date, publisher_name, developer_name,
                    description, raw_payload_path, updated_at
                ) VALUES (?, 'igdb', ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(source, source_app_id) DO UPDATE SET
                    name=excluded.name,
                    genre=excluded.genre,
                    platform=excluded.platform,
                    release_date=excluded.release_date,
                    publisher_name=excluded.publisher_name,
                    developer_name=excluded.developer_name,
                    description=excluded.description,
                    raw_payload_path=excluded.raw_payload_path,
                    updated_at=datetime('now')
                """,
                (
                    game_id_igdb, game.get("name") or f"IGDB_{game_id_igdb}",
                    genre_name, platform_str, release_iso,
                    pub_name, dev_name,
                    (game.get("summary") or "")[:500],
                    raw_path_str,
                ),
            )
            row = conn.execute(
                "SELECT game_id FROM dim_game WHERE source='igdb' AND source_app_id=?",
                (game_id_igdb,),
            ).fetchone()
            return row["game_id"]

    # ---- Main entry ------------------------------------------------------
    def run(self, max_items: int = 100) -> dict[str, int]:
        today = date.today().isoformat()
        logger.info(f"[igdb] starting crawl, limit={max_items}")

        games = self.fetch_top_games(limit=max_items)
        if not games:
            logger.warning("[igdb] no games returned — abort")
            return {"games_crawled": 0}

        # Save raw payload (list)
        raw_path = self.save_raw(f"top_games_{today}", games, today)
        raw_path_rel = str(raw_path.relative_to(PROJECT_ROOT))

        games_ok = 0
        for game in games:
            try:
                self.upsert_game_row(game, raw_path_rel)
                games_ok += 1
            except Exception as e:
                logger.warning(f"[igdb] upsert game {game.get('id')} failed: {e}")

        logger.success(f"[igdb] DONE: {games_ok}/{len(games)} games upserted")
        return {"games_crawled": games_ok}
