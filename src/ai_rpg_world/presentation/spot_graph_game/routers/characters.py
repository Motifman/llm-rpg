"""Character CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    CharacterDetailResponse,
    CharacterListResponse,
    CharacterUpdateRequest,
)
from ai_rpg_world.presentation.spot_graph_game.dependencies import get_runtime_manager

router = APIRouter(prefix="/characters", tags=["characters"])


@router.get("", response_model=CharacterListResponse)
async def list_characters() -> CharacterListResponse:
    manager = get_runtime_manager()
    characters = manager.list_characters()
    return CharacterListResponse(characters=characters)


@router.get("/{character_id}", response_model=CharacterDetailResponse)
async def get_character(character_id: str) -> CharacterDetailResponse:
    manager = get_runtime_manager()
    character = manager.get_character(character_id)
    if character is None:
        raise HTTPException(
            status_code=404, detail=f"Character not found: {character_id}"
        )
    return character


@router.post("", response_model=CharacterDetailResponse, status_code=201)
async def create_character(request: CharacterCreateRequest) -> CharacterDetailResponse:
    manager = get_runtime_manager()
    return manager.create_character(request)


@router.put("/{character_id}", response_model=CharacterDetailResponse)
async def update_character(
    character_id: str, request: CharacterUpdateRequest
) -> CharacterDetailResponse:
    manager = get_runtime_manager()
    updated = manager.update_character(character_id, request)
    if updated is None:
        raise HTTPException(
            status_code=404, detail=f"Character not found: {character_id}"
        )
    return updated
