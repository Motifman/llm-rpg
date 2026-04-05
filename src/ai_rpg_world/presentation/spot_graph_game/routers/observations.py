"""Game observation endpoints — spot view, event log, inventory."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ai_rpg_world.presentation.spot_graph_game.schemas import (
    EventLogResponse,
    InventoryResponse,
    SpotViewResponse,
)
from ai_rpg_world.presentation.spot_graph_game.dependencies import get_runtime_manager

router = APIRouter(prefix="/sessions/{session_id}", tags=["observations"])


@router.get("/view", response_model=SpotViewResponse)
async def get_current_view(
    session_id: str,
    character_id: str | None = Query(default=None),
    spot_id: str | None = Query(default=None),
) -> SpotViewResponse:
    """Get the current spot view.

    If *character_id* is provided, returns the spot where that character is
    (tracking mode). If *spot_id* is provided, returns that spot directly
    (fixed-camera mode). If neither, returns the default tracked character's
    spot.
    """
    manager = get_runtime_manager()
    view = manager.get_spot_view(session_id, character_id=character_id, spot_id=spot_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Session or spot not found")
    return view


@router.get("/log", response_model=EventLogResponse)
async def get_event_log(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EventLogResponse:
    manager = get_runtime_manager()
    log = manager.get_event_log(session_id, limit=limit, offset=offset)
    if log is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return log


@router.get(
    "/inventory/{character_id}", response_model=InventoryResponse
)
async def get_inventory(session_id: str, character_id: str) -> InventoryResponse:
    manager = get_runtime_manager()
    inv = manager.get_inventory(session_id, character_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Session or character not found")
    return inv
