"""Chat (voice-from-beyond) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_rpg_world.presentation.spot_graph_game.schemas import (
    ChatHistoryResponse,
    ChatSendRequest,
    ChatMessageResponse,
)
from ai_rpg_world.presentation.spot_graph_game.dependencies import get_runtime_manager

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/send", response_model=ChatMessageResponse)
async def send_message(request: ChatSendRequest) -> ChatMessageResponse:
    """Send a message as the 'voice from beyond' to a character or scope."""
    manager = get_runtime_manager()
    return manager.send_chat_message(request)


@router.get(
    "/history/{character_id}", response_model=ChatHistoryResponse
)
async def get_chat_history(character_id: str) -> ChatHistoryResponse:
    manager = get_runtime_manager()
    history = manager.get_chat_history(character_id)
    if history is None:
        raise HTTPException(
            status_code=404, detail=f"Character not found: {character_id}"
        )
    return history
