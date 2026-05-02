"""Application-level dependency holder for the spot-graph game.

This module acts as a lightweight service locator that the FastAPI routers
reference.  The singleton is set once at application startup by the app
factory and remains immutable for the lifetime of the process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
        GameRuntimeManager,
    )

_manager: Optional["GameRuntimeManager"] = None


def set_runtime_manager(manager: "GameRuntimeManager") -> None:
    global _manager
    _manager = manager


def get_runtime_manager() -> "GameRuntimeManager":
    if _manager is None:
        raise RuntimeError(
            "GameRuntimeManager has not been initialised. "
            "Call set_runtime_manager() during application startup."
        )
    return _manager
