"""FastAPI application factory for the spot-graph virtual world game."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_rpg_world.presentation.spot_graph_game.dependencies import (
    set_runtime_manager,
)
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
)
from ai_rpg_world.presentation.spot_graph_game.routers import (
    characters,
    chat,
    observations,
    results,
    saves,
    sessions,
    worlds,
)
from ai_rpg_world.presentation.spot_graph_game.websocket_handler import (
    game_event_websocket,
)


def create_game_app(
    *,
    scenarios_dir: Path | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Build the FastAPI application for the virtual world game.

    Parameters
    ----------
    scenarios_dir:
        Directory containing scenario JSON files.  Defaults to
        ``data/scenarios`` relative to the project root.
    cors_origins:
        Allowed CORS origins.  Defaults to common local-dev addresses.
    """
    if scenarios_dir is None:
        scenarios_dir = Path("data/scenarios")
    if cors_origins is None:
        cors_origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    manager = GameRuntimeManager(scenarios_dir=scenarios_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        set_runtime_manager(manager)
        yield

    app = FastAPI(
        title="Virtual World AI Character Game",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(worlds.router, prefix="/api")
    app.include_router(characters.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(observations.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(results.router, prefix="/api")
    app.include_router(saves.router, prefix="/api")

    app.websocket("/api/sessions/{session_id}/events")(game_event_websocket)

    @app.get("/api/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app
