"""World listing and detail endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_rpg_world.presentation.spot_graph_game.schemas import (
    WorldDetailResponse,
    WorldListResponse,
    WorldSummaryResponse,
)
from ai_rpg_world.presentation.spot_graph_game.dependencies import get_runtime_manager

router = APIRouter(prefix="/worlds", tags=["worlds"])


@router.get("", response_model=WorldListResponse)
async def list_worlds() -> WorldListResponse:
    manager = get_runtime_manager()
    worlds = manager.list_available_worlds()
    return WorldListResponse(worlds=worlds)


@router.get("/{world_id}", response_model=WorldDetailResponse)
async def get_world_detail(world_id: str) -> WorldDetailResponse:
    manager = get_runtime_manager()
    detail = manager.get_world_detail(world_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"World not found: {world_id}")
    return detail
