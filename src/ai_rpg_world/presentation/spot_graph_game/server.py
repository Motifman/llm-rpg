"""CLI entry point for the spot-graph virtual world game server."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from ai_rpg_world.presentation.spot_graph_game.app import create_game_app


def create_app_from_env():
    """Factory used by ``uvicorn --factory``."""
    scenarios_dir = Path(
        os.getenv("GAME_SCENARIOS_DIR", "data/scenarios")
    )
    cors_raw = os.getenv(
        "GAME_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
    return create_game_app(
        scenarios_dir=scenarios_dir,
        cors_origins=cors_origins,
    )


def main() -> None:
    host = os.getenv("GAME_HOST", "127.0.0.1")
    port = int(os.getenv("GAME_PORT", "8080"))
    reload = os.getenv("GAME_RELOAD", "false").lower() in ("1", "true", "yes")

    uvicorn.run(
        "ai_rpg_world.presentation.spot_graph_game.server:create_app_from_env",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
