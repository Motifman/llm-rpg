"""Pydantic schemas for the spot-graph game API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── World ──


class WorldSummaryResponse(BaseModel):
    id: str
    title: str
    description: str
    theme: str
    difficulty: str
    estimated_ticks: int
    tags: list[str] = Field(default_factory=list)
    thumbnail_url: str | None = None


class WorldDetailResponse(WorldSummaryResponse):
    spots_count: int
    items_count: int
    connections_count: int


class WorldListResponse(BaseModel):
    worlds: list[WorldSummaryResponse]


# ── Character ──


class CharacterSummaryResponse(BaseModel):
    id: str
    name: str
    age_image: str | None = None
    personality_tags: list[str] = Field(default_factory=list)
    portrait_url: str | None = None
    icon_url: str | None = None


class CharacterDetailResponse(CharacterSummaryResponse):
    first_person: str = ""
    appearance: str = ""
    speech_samples: list[str] = Field(default_factory=list)
    fragmented_memory: str = ""
    values: str = ""
    strengths: str = ""
    weaknesses: str = ""
    interpersonal_tendency: str = ""
    behavioral_rules: list[str] = Field(default_factory=list)


class CharacterCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    first_person: str = Field(default="私", max_length=10)
    age_image: str | None = None
    appearance: str = ""
    personality_tags: list[str] = Field(default_factory=list)
    speech_samples: list[str] = Field(default_factory=list)
    fragmented_memory: str = ""
    values: str = ""
    strengths: str = ""
    weaknesses: str = ""
    interpersonal_tendency: str = ""
    behavioral_rules: list[str] = Field(default_factory=list)


class CharacterUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    first_person: str | None = Field(default=None, max_length=10)
    age_image: str | None = None
    appearance: str | None = None
    personality_tags: list[str] | None = None
    speech_samples: list[str] | None = None
    fragmented_memory: str | None = None
    values: str | None = None
    strengths: str | None = None
    weaknesses: str | None = None
    interpersonal_tendency: str | None = None
    behavioral_rules: list[str] | None = None


class CharacterListResponse(BaseModel):
    characters: list[CharacterSummaryResponse]


# ── Session ──


class SessionCreateRequest(BaseModel):
    world_id: str
    character_ids: list[str] = Field(..., min_length=1, max_length=5)


class SessionSummaryResponse(BaseModel):
    session_id: str
    world_id: str
    world_title: str
    status: str
    current_tick: int
    character_ids: list[str]
    created_at: str


class SessionStateResponse(BaseModel):
    session_id: str
    status: str
    current_tick: int
    game_time_label: str
    is_ended: bool
    end_result: str | None = None
    end_reason: str | None = None


class SpeedChangeRequest(BaseModel):
    speed_multiplier: float = Field(..., gt=0, le=5.0)


# ── Game View ──


class SpotViewResponse(BaseModel):
    spot_id: str
    spot_name: str
    spot_description: str
    background_image_key: str
    atmosphere: dict[str, Any] | None = None
    characters_present: list[CharacterInSpotResponse] = Field(default_factory=list)
    objects: list[SpotObjectResponse] = Field(default_factory=list)
    connections: list[SpotConnectionResponse] = Field(default_factory=list)


class CharacterInSpotResponse(BaseModel):
    character_id: str
    name: str
    icon_url: str | None = None
    mini_sprite_key: str = "idle"
    is_tracked: bool = False


class SpotObjectResponse(BaseModel):
    object_id: str
    name: str
    description: str
    object_type: str
    state: dict[str, Any] = Field(default_factory=dict)
    available_actions: list[str] = Field(default_factory=list)


class SpotConnectionResponse(BaseModel):
    connection_id: str
    target_spot_id: str
    target_spot_name: str
    name: str
    is_passable: bool
    icon_url: str | None = None


class InventoryItemResponse(BaseModel):
    item_spec_id: str
    name: str
    description: str
    quantity: int
    icon_url: str | None = None


class InventoryResponse(BaseModel):
    character_id: str
    items: list[InventoryItemResponse] = Field(default_factory=list)


# ── Event Log ──


class EventLogEntry(BaseModel):
    tick: int
    game_time_label: str
    timestamp: str
    text: str
    event_type: str = "general"
    actor_id: str | None = None
    actor_name: str | None = None


class EventLogResponse(BaseModel):
    entries: list[EventLogEntry] = Field(default_factory=list)
    has_more: bool = False


# ── Chat ──


class ChatSendRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=2000)
    target_character_id: str = Field(..., min_length=1)
    scope: str = Field(default="individual", pattern=r"^(individual|spot|world)$")


class ChatMessageResponse(BaseModel):
    sender: str
    message: str
    timestamp: str
    is_player: bool


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse] = Field(default_factory=list)


# ── Result ──


class CharacterImpressionResponse(BaseModel):
    character_id: str
    name: str
    portrait_url: str | None = None
    impression_text: str


class ResultImpressionResponse(BaseModel):
    impressions: list[CharacterImpressionResponse] = Field(default_factory=list)


class TimelineEventResponse(BaseModel):
    tick: int
    game_time_label: str
    character_id: str
    character_name: str
    event_type: str
    description: str


class ResultTimelineResponse(BaseModel):
    events: list[TimelineEventResponse] = Field(default_factory=list)
    total_ticks: int = 0


class RelationshipEdge(BaseModel):
    from_character_id: str
    from_name: str
    to_character_id: str
    to_name: str
    interaction_count: int


class ResultRelationshipResponse(BaseModel):
    characters: list[CharacterSummaryResponse] = Field(default_factory=list)
    edges: list[RelationshipEdge] = Field(default_factory=list)


# ── Save ──


class SaveSlotResponse(BaseModel):
    save_id: str
    session_id: str
    world_title: str
    current_tick: int
    saved_at: str


class SaveListResponse(BaseModel):
    saves: list[SaveSlotResponse] = Field(default_factory=list)


# ── WebSocket Events ──


class GameEventMessage(BaseModel):
    type: str
    tick: int
    game_time_label: str
    data: dict[str, Any] = Field(default_factory=dict)
