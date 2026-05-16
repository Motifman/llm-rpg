"""FastAPI application factory for the spot-graph virtual world game."""

from __future__ import annotations

import logging
import math
import os
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
from ai_rpg_world.presentation.spot_graph_game.tick_loop import (
    SimulationTickLoop,
)
from ai_rpg_world.presentation.spot_graph_game.websocket_handler import (
    game_event_websocket,
)

logger = logging.getLogger(__name__)


_ENV_TICK_INTERVAL = "SPOT_GRAPH_TICK_INTERVAL_SEC"
_ENV_TICK_LOOP_ENABLED = "SPOT_GRAPH_TICK_LOOP_ENABLED"
_DEFAULT_TICK_INTERVAL_SEC = 1.0
_MIN_SAFE_INTERVAL_SEC = 0.01


def _read_tick_loop_config() -> tuple[bool, float]:
    """Parse env vars controlling the background tick loop.

    Disabled by setting ``SPOT_GRAPH_TICK_LOOP_ENABLED`` to a falsy value;
    this is important for unit/integration tests that don't want a
    background task firing while the FastAPI ``TestClient`` is alive.
    """
    enabled_raw = os.getenv(_ENV_TICK_LOOP_ENABLED, "true").strip().lower()
    enabled = enabled_raw in ("1", "true", "yes", "on")
    try:
        interval = float(
            os.getenv(_ENV_TICK_INTERVAL, str(_DEFAULT_TICK_INTERVAL_SEC))
        )
    except ValueError:
        logger.warning(
            "Invalid %s value; falling back to %.3fs",
            _ENV_TICK_INTERVAL,
            _DEFAULT_TICK_INTERVAL_SEC,
        )
        interval = _DEFAULT_TICK_INTERVAL_SEC
    # Guard against zero / negative / NaN / inf so the loop constructor does
    # not raise during FastAPI startup and crash the whole server.
    # float("nan") < x は False になるため、明示的に isfinite チェックを噛ます。
    if not math.isfinite(interval) or interval < _MIN_SAFE_INTERVAL_SEC:
        logger.warning(
            "%s=%s is invalid or below the safe minimum (%.3fs); "
            "falling back to %.3fs",
            _ENV_TICK_INTERVAL,
            interval,
            _MIN_SAFE_INTERVAL_SEC,
            _DEFAULT_TICK_INTERVAL_SEC,
        )
        interval = _DEFAULT_TICK_INTERVAL_SEC
    return enabled, interval


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
    tick_loop_enabled, tick_interval = _read_tick_loop_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        set_runtime_manager(manager)
        tick_loop: SimulationTickLoop | None = None
        if tick_loop_enabled:
            tick_loop = SimulationTickLoop(
                manager=manager,
                interval_seconds=tick_interval,
            )
            tick_loop.start()
            logger.info(
                "Spot graph tick loop enabled (interval=%.3fs)", tick_interval
            )
        else:
            logger.info("Spot graph tick loop disabled via %s", _ENV_TICK_LOOP_ENABLED)
        try:
            yield
        finally:
            if tick_loop is not None:
                # Suppress errors so a stop() failure does not mask any
                # exception that was already propagating through yield.
                try:
                    await tick_loop.stop()
                except Exception:
                    logger.exception("Tick loop stop() raised on shutdown")

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
