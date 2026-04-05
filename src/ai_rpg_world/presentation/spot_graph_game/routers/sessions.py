"""Game session lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ai_rpg_world.presentation.spot_graph_game.schemas import (
    SessionCreateRequest,
    SessionStateResponse,
    SessionSummaryResponse,
    SpeedChangeRequest,
)
from ai_rpg_world.presentation.spot_graph_game.dependencies import get_runtime_manager

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionSummaryResponse, status_code=201)
async def create_session(request: SessionCreateRequest) -> SessionSummaryResponse:
    manager = get_runtime_manager()
    return manager.create_session(request)


@router.get("/{session_id}", response_model=SessionStateResponse)
async def get_session_state(session_id: str) -> SessionStateResponse:
    manager = get_runtime_manager()
    state = manager.get_session_state(session_id)
    if state is None:
        raise HTTPException(
            status_code=404, detail=f"Session not found: {session_id}"
        )
    return state


@router.post("/{session_id}/pause")
async def pause_session(session_id: str) -> Response:
    manager = get_runtime_manager()
    if not manager.pause_session(session_id):
        raise HTTPException(
            status_code=404, detail=f"Session not found: {session_id}"
        )
    return Response(status_code=204)


@router.post("/{session_id}/resume")
async def resume_session(session_id: str) -> Response:
    manager = get_runtime_manager()
    if not manager.resume_session(session_id):
        raise HTTPException(
            status_code=404, detail=f"Session not found: {session_id}"
        )
    return Response(status_code=204)


@router.post("/{session_id}/stop")
async def stop_session(session_id: str) -> Response:
    manager = get_runtime_manager()
    if not manager.stop_session(session_id):
        raise HTTPException(
            status_code=404, detail=f"Session not found: {session_id}"
        )
    return Response(status_code=204)


@router.post("/{session_id}/speed")
async def change_speed(session_id: str, request: SpeedChangeRequest) -> Response:
    manager = get_runtime_manager()
    if not manager.set_session_speed(session_id, request.speed_multiplier):
        raise HTTPException(
            status_code=404, detail=f"Session not found: {session_id}"
        )
    return Response(status_code=204)
