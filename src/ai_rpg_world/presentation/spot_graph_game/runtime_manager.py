"""Central manager that bridges FastAPI routers with the game runtime.

This is a *stub* that defines the interface the routers depend on.
Actual wiring to ``EscapeGameRuntime`` / scenario loaders / LLM
orchestration will be implemented incrementally as each feature slice
lands.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    CharacterDetailResponse,
    CharacterSummaryResponse,
    CharacterUpdateRequest,
    ChatHistoryResponse,
    ChatMessageResponse,
    ChatSendRequest,
    EventLogResponse,
    InventoryResponse,
    ResultImpressionResponse,
    ResultRelationshipResponse,
    ResultTimelineResponse,
    SaveListResponse,
    SaveSlotResponse,
    SessionCreateRequest,
    SessionStateResponse,
    SessionSummaryResponse,
    SpeedChangeRequest,
    SpotViewResponse,
    WorldDetailResponse,
    WorldSummaryResponse,
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GameRuntimeManager:
    """Facade consumed by all API routers.

    Each method corresponds 1-to-1 with a router action. Methods that
    currently lack a backend implementation return placeholder data so that
    the API can be exercised end-to-end while the rest of the stack is
    built.
    """

    scenarios_dir: Path = field(default_factory=lambda: Path("data/scenarios"))

    # ── Worlds ──

    def list_available_worlds(self) -> list[WorldSummaryResponse]:
        worlds: list[WorldSummaryResponse] = []
        if not self.scenarios_dir.exists():
            return worlds
        for path in sorted(self.scenarios_dir.glob("*.json")):
            worlds.append(
                WorldSummaryResponse(
                    id=path.stem,
                    title=path.stem.replace("_", " ").title(),
                    description="",
                    theme="",
                    difficulty="medium",
                    estimated_ticks=120,
                    tags=[],
                )
            )
        return worlds

    def get_world_detail(self, world_id: str) -> Optional[WorldDetailResponse]:
        path = self.scenarios_dir / f"{world_id}.json"
        if not path.exists():
            return None
        return WorldDetailResponse(
            id=world_id,
            title=world_id.replace("_", " ").title(),
            description="",
            theme="",
            difficulty="medium",
            estimated_ticks=120,
            tags=[],
            spots_count=0,
            items_count=0,
            connections_count=0,
        )

    # ── Characters ──

    def list_characters(self) -> list[CharacterSummaryResponse]:
        return []

    def get_character(self, character_id: str) -> Optional[CharacterDetailResponse]:
        return None

    def create_character(
        self, request: CharacterCreateRequest
    ) -> CharacterDetailResponse:
        cid = uuid.uuid4().hex[:8]
        return CharacterDetailResponse(
            id=cid,
            name=request.name,
            personality_tags=request.personality_tags,
            first_person=request.first_person,
            appearance=request.appearance,
            speech_samples=request.speech_samples,
            fragmented_memory=request.fragmented_memory,
            values=request.values,
            strengths=request.strengths,
            weaknesses=request.weaknesses,
            interpersonal_tendency=request.interpersonal_tendency,
        )

    def update_character(
        self, character_id: str, request: CharacterUpdateRequest
    ) -> Optional[CharacterDetailResponse]:
        return None

    # ── Sessions ──

    def create_session(
        self, request: SessionCreateRequest
    ) -> SessionSummaryResponse:
        sid = uuid.uuid4().hex[:12]
        return SessionSummaryResponse(
            session_id=sid,
            world_id=request.world_id,
            world_title=request.world_id.replace("_", " ").title(),
            status="running",
            current_tick=0,
            character_ids=request.character_ids,
            created_at=_utcnow_iso(),
        )

    def get_session_state(
        self, session_id: str
    ) -> Optional[SessionStateResponse]:
        return None

    def pause_session(self, session_id: str) -> bool:
        return False

    def resume_session(self, session_id: str) -> bool:
        return False

    def stop_session(self, session_id: str) -> bool:
        return False

    def set_session_speed(
        self, session_id: str, speed_multiplier: float
    ) -> bool:
        return False

    # ── Observations ──

    def get_spot_view(
        self,
        session_id: str,
        *,
        character_id: Optional[str] = None,
        spot_id: Optional[str] = None,
    ) -> Optional[SpotViewResponse]:
        return None

    def get_event_log(
        self, session_id: str, *, limit: int = 50, offset: int = 0
    ) -> Optional[EventLogResponse]:
        return None

    def get_inventory(
        self, session_id: str, character_id: str
    ) -> Optional[InventoryResponse]:
        return None

    # ── Chat ──

    def send_chat_message(
        self, request: ChatSendRequest
    ) -> ChatMessageResponse:
        return ChatMessageResponse(
            sender="player",
            message=request.message,
            timestamp=_utcnow_iso(),
            is_player=True,
        )

    def get_chat_history(
        self, character_id: str
    ) -> Optional[ChatHistoryResponse]:
        return None

    # ── Results ──

    def get_result_impressions(
        self, session_id: str
    ) -> Optional[ResultImpressionResponse]:
        return None

    def get_result_timeline(
        self, session_id: str
    ) -> Optional[ResultTimelineResponse]:
        return None

    def get_result_relationships(
        self, session_id: str
    ) -> Optional[ResultRelationshipResponse]:
        return None

    # ── Saves ──

    def list_saves(self) -> SaveListResponse:
        return SaveListResponse()

    def save_session(self, session_id: str) -> Optional[SaveSlotResponse]:
        return None

    def load_save(self, save_id: str) -> Optional[SaveSlotResponse]:
        return None
