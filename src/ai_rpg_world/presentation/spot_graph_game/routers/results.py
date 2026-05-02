"""Result screen data endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_rpg_world.presentation.spot_graph_game.schemas import (
    ResultImpressionResponse,
    ResultRelationshipResponse,
    ResultTimelineResponse,
)
from ai_rpg_world.presentation.spot_graph_game.dependencies import get_runtime_manager

router = APIRouter(prefix="/sessions/{session_id}/results", tags=["results"])


@router.get("/impressions", response_model=ResultImpressionResponse)
async def get_impressions(session_id: str) -> ResultImpressionResponse:
    manager = get_runtime_manager()
    impressions = manager.get_result_impressions(session_id)
    if impressions is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return impressions


@router.get("/timeline", response_model=ResultTimelineResponse)
async def get_timeline(session_id: str) -> ResultTimelineResponse:
    manager = get_runtime_manager()
    timeline = manager.get_result_timeline(session_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return timeline


@router.get("/relationships", response_model=ResultRelationshipResponse)
async def get_relationships(session_id: str) -> ResultRelationshipResponse:
    manager = get_runtime_manager()
    relationships = manager.get_result_relationships(session_id)
    if relationships is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return relationships
