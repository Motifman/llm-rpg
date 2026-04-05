"""Save / load endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_rpg_world.presentation.spot_graph_game.schemas import (
    SaveListResponse,
    SaveSlotResponse,
)
from ai_rpg_world.presentation.spot_graph_game.dependencies import get_runtime_manager

router = APIRouter(prefix="/saves", tags=["saves"])


@router.get("", response_model=SaveListResponse)
async def list_saves() -> SaveListResponse:
    manager = get_runtime_manager()
    return manager.list_saves()


@router.post("", response_model=SaveSlotResponse, status_code=201)
async def create_save(session_id: str) -> SaveSlotResponse:
    manager = get_runtime_manager()
    save = manager.save_session(session_id)
    if save is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return save


@router.post("/{save_id}/load", response_model=SaveSlotResponse)
async def load_save(save_id: str) -> SaveSlotResponse:
    manager = get_runtime_manager()
    result = manager.load_save(save_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Save not found")
    return result
