"""
Serve Game BI API — uvicorn runner.

Usage:
    python scripts/serve_api.py                      # localhost:8000
    python scripts/serve_api.py --host 0.0.0.0       # LAN accessible
    python scripts/serve_api.py --port 9000          # custom port
    python scripts/serve_api.py --reload             # dev mode (auto-reload)

Expose ra internet (cloudflare tunnel — chạy terminal khác):
    cloudflared tunnel --url http://localhost:8000

Power BI access:
    - Endpoint: http://<host>:8000/api/gacha/revenue?format=csv
    - Header: X-API-Key: <key từ .env>
    - Connector: Get Data → Web → Advanced → URL + HTTP header
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config import API_KEY, LOG_LEVEL, ensure_dirs

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)


@click.command()
@click.option("--host", default="127.0.0.1",
              help="Bind host (127.0.0.1 = localhost only, 0.0.0.0 = LAN)")
@click.option("--port", default=8000, type=int, help="Port")
@click.option("--reload", is_flag=True, default=False,
              help="Dev mode: auto-reload on file change")
def main(host: str, port: int, reload: bool):
    """Chạy FastAPI server."""
    ensure_dirs()

    if not API_KEY:
        logger.warning(
            "⚠ API_KEY chưa set trong .env — API chạy ở DEV MODE (no auth). "
            "Chỉ an toàn nếu bind localhost. Set API_KEY trước khi expose LAN/internet."
        )
        if host != "127.0.0.1":
            logger.error(
                "❌ Refuse bind non-localhost khi không có API_KEY. "
                "Set API_KEY trong .env rồi chạy lại."
            )
            sys.exit(1)

    logger.info(f"=== GAME BI API | host={host}, port={port}, reload={reload} ===")
    logger.info(f"API_KEY: {'set ✓' if API_KEY else 'NOT SET (dev mode)'}")
    logger.info(f"Docs: http://{host}:{port}/docs")
    logger.info(f"Sample: http://{host}:{port}/api/gacha/revenue?format=csv")

    import uvicorn
    uvicorn.run(
        "src.api.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level=LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
