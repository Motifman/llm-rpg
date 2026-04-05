"""Central manager that bridges FastAPI routers with the game runtime.

Wires ``EscapeGameRuntime`` / scenario loaders / session lifecycle to
the API layer.  Methods that are not yet backed by real logic return
stub data so that the full API surface remains exercisable.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMappingError
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    CharacterDetailResponse,
    CharacterInSpotResponse,
    CharacterSummaryResponse,
    CharacterUpdateRequest,
    ChatHistoryResponse,
    ChatMessageResponse,
    ChatSendRequest,
    EventLogResponse,
    InventoryItemResponse,
    InventoryResponse,
    ResultImpressionResponse,
    ResultRelationshipResponse,
    ResultTimelineResponse,
    SaveListResponse,
    SaveSlotResponse,
    SessionCreateRequest,
    SessionStateResponse,
    SessionSummaryResponse,
    SpotConnectionResponse,
    SpotObjectResponse,
    SpotViewResponse,
    WorldDetailResponse,
    WorldSummaryResponse,
)

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_get_str(mapper: Any, namespace: str, numeric_id: int) -> str:
    """Return the string ID for *numeric_id*, falling back to str(numeric_id)."""
    try:
        return mapper.get_str(namespace, numeric_id)
    except (ScenarioIdMappingError, KeyError):
        return str(numeric_id)


def _read_scenario_metadata(path: Path) -> Optional[Dict[str, Any]]:
    """Read only the metadata section from a scenario JSON without full parse."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return raw
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read scenario %s: %s", path, exc)
        return None


@dataclass
class _SessionState:
    """Lightweight bookkeeping for a running game session."""

    session_id: str
    world_id: str
    world_title: str
    character_ids: list[str]
    status: str  # "running" | "paused" | "ended"
    created_at: str
    speed_multiplier: float = 1.0

    runtime: Any = field(default=None, repr=False)


@dataclass
class GameRuntimeManager:
    """Facade consumed by all API routers."""

    scenarios_dir: Path = field(default_factory=lambda: Path("data/scenarios"))

    _scenario_cache: Dict[str, Dict[str, Any]] = field(
        default_factory=dict, repr=False
    )
    _sessions: Dict[str, _SessionState] = field(
        default_factory=dict, repr=False
    )

    # ── Worlds ──

    def _load_scenario_raw(self, world_id: str) -> Optional[Dict[str, Any]]:
        if world_id in self._scenario_cache:
            return self._scenario_cache[world_id]
        path = self.scenarios_dir / f"{world_id}.json"
        if not path.exists():
            return None
        raw = _read_scenario_metadata(path)
        if raw is not None:
            self._scenario_cache[world_id] = raw
        return raw

    def list_available_worlds(self) -> list[WorldSummaryResponse]:
        worlds: list[WorldSummaryResponse] = []
        if not self.scenarios_dir.exists():
            return worlds
        for path in sorted(self.scenarios_dir.glob("*.json")):
            raw = self._load_scenario_raw(path.stem)
            if raw is None:
                continue
            meta = raw.get("metadata", {})
            worlds.append(
                WorldSummaryResponse(
                    id=meta.get("id", path.stem),
                    title=meta.get("title", path.stem),
                    description=meta.get("description", ""),
                    theme=meta.get("theme", ""),
                    difficulty=meta.get("difficulty", "medium"),
                    estimated_ticks=int(meta.get("estimated_ticks", 100)),
                    tags=list(meta.get("tags", [])),
                )
            )
        return worlds

    def get_world_detail(self, world_id: str) -> Optional[WorldDetailResponse]:
        raw = self._load_scenario_raw(world_id)
        if raw is None:
            return None
        meta = raw.get("metadata", {})
        return WorldDetailResponse(
            id=meta.get("id", world_id),
            title=meta.get("title", world_id),
            description=meta.get("description", ""),
            theme=meta.get("theme", ""),
            difficulty=meta.get("difficulty", "medium"),
            estimated_ticks=int(meta.get("estimated_ticks", 100)),
            tags=list(meta.get("tags", [])),
            spots_count=len(raw.get("spots", [])),
            items_count=len(raw.get("item_specs", [])),
            connections_count=len(raw.get("connections", [])),
        )

    # ── Characters (stub — persistence TBD) ──

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
        scenario_path = self.scenarios_dir / f"{request.world_id}.json"
        if not scenario_path.exists():
            raise ValueError(f"World not found: {request.world_id}")

        from demos.escape_game.escape_game_runtime import (
            create_escape_game_runtime,
        )

        runtime = create_escape_game_runtime(scenario_path)

        sid = uuid.uuid4().hex[:12]
        title = runtime.metadata.title
        state = _SessionState(
            session_id=sid,
            world_id=request.world_id,
            world_title=title,
            character_ids=request.character_ids,
            status="running",
            created_at=_utcnow_iso(),
            runtime=runtime,
        )
        self._sessions[sid] = state
        logger.info("Session %s created for world %s", sid, request.world_id)
        return SessionSummaryResponse(
            session_id=sid,
            world_id=request.world_id,
            world_title=title,
            status="running",
            current_tick=0,
            character_ids=request.character_ids,
            created_at=state.created_at,
        )

    def get_session_state(
        self, session_id: str
    ) -> Optional[SessionStateResponse]:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        runtime = state.runtime
        tick = runtime.current_tick() if runtime else 0
        hours = (tick * 5) % (24 * 60)
        h, m = divmod(hours, 60)
        time_label = f"{h}:{m:02d}"

        is_ended = False
        end_result = None
        end_reason = None
        if runtime:
            result = runtime.check_game_end()
            is_ended = result.is_ended
            if is_ended:
                end_result = str(result.result) if result.result else None
                end_reason = result.reason
                state.status = "ended"

        return SessionStateResponse(
            session_id=session_id,
            status=state.status,
            current_tick=tick,
            game_time_label=time_label,
            is_ended=is_ended,
            end_result=end_result,
            end_reason=end_reason,
        )

    def pause_session(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.status = "paused"
        return True

    def resume_session(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.status = "running"
        return True

    def stop_session(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.status = "ended"
        return True

    def set_session_speed(
        self, session_id: str, speed_multiplier: float
    ) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.speed_multiplier = speed_multiplier
        return True

    # ── Observations ──

    def get_spot_view(
        self,
        session_id: str,
        *,
        character_id: Optional[str] = None,
        spot_id: Optional[str] = None,
    ) -> Optional[SpotViewResponse]:
        state = self._sessions.get(session_id)
        if state is None or state.runtime is None:
            return None

        runtime = state.runtime
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        graph = runtime._spot_graph_repo.find_graph()

        if spot_id is not None:
            target_spot_int = runtime.id_mapper.get_int("spot", spot_id)
            from ai_rpg_world.domain.world.value_object.spot_id import SpotId
            target_spot_id = SpotId.create(target_spot_int)
        elif character_id is not None:
            pid_int = runtime.id_mapper.get_int("player", character_id)
            eid = EntityId.create(pid_int)
            target_spot_id = graph.get_entity_spot(eid)
        else:
            first_spawn = runtime.scenario.player_spawns[0]
            eid = EntityId.create(first_spawn.player_id)
            target_spot_id = graph.get_entity_spot(eid)

        spot_node = graph.get_spot(target_spot_id)
        interior = runtime._spot_interior_repo.find_by_spot_id(target_spot_id)

        characters: list[CharacterInSpotResponse] = []
        presence = graph.presence_at(target_spot_id)
        for eid_val in presence.present_entity_ids:
            eid_int = eid_val.value if hasattr(eid_val, "value") else int(eid_val)
            name = runtime.get_player_name(PlayerId(eid_int))
            spawn = next(
                (s for s in runtime.scenario.player_spawns if s.player_id == eid_int),
                None,
            )
            str_id = spawn.string_id if spawn else str(eid_val)
            characters.append(CharacterInSpotResponse(
                character_id=str_id,
                name=name,
            ))

        objects: list[SpotObjectResponse] = []
        if interior:
            for obj in interior.objects:
                actions = [i.action_name for i in obj.interactions]
                obj_str = _safe_get_str(runtime.id_mapper, "object", obj.object_id.value)
                objects.append(SpotObjectResponse(
                    object_id=obj_str,
                    name=obj.name,
                    description=obj.description,
                    object_type=obj.object_type.name,
                    state=dict(obj.state),
                    available_actions=actions,
                ))

        connections: list[SpotConnectionResponse] = []
        for conn in graph.iter_outgoing_connections_from(target_spot_id):
            target_node = graph.get_spot(conn.to_spot_id)
            conn_str = _safe_get_str(runtime.id_mapper, "connection", conn.connection_id.value)
            connections.append(SpotConnectionResponse(
                connection_id=conn_str,
                target_spot_id=_safe_get_str(runtime.id_mapper, "spot", conn.to_spot_id.value),
                target_spot_name=target_node.name,
                name=conn.name,
                is_passable=conn.is_passable,
            ))

        spot_str = _safe_get_str(runtime.id_mapper, "spot", target_spot_id.value)
        return SpotViewResponse(
            spot_id=spot_str,
            spot_name=spot_node.name,
            spot_description=spot_node.description,
            background_image_key=spot_str,
            atmosphere={
                "lighting": spot_node.atmosphere.lighting.name,
                "sound_ambient": spot_node.atmosphere.sound_ambient,
                "temperature": spot_node.atmosphere.temperature.name,
                "smell": spot_node.atmosphere.smell,
            } if spot_node.atmosphere else None,
            characters_present=characters,
            objects=objects,
            connections=connections,
        )

    def get_event_log(
        self, session_id: str, *, limit: int = 50, offset: int = 0
    ) -> Optional[EventLogResponse]:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return EventLogResponse()

    def get_inventory(
        self, session_id: str, character_id: str
    ) -> Optional[InventoryResponse]:
        state = self._sessions.get(session_id)
        if state is None or state.runtime is None:
            return None

        runtime = state.runtime
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        pid_int = runtime.id_mapper.get_int("player", character_id)
        pid = PlayerId(pid_int)
        inv = runtime._player_inventory_repo.find_by_id(pid)
        items: list[InventoryItemResponse] = []
        if inv:
            from ai_rpg_world.domain.player.value_object.slot_id import SlotId

            counts: dict[int, int] = {}
            specs: dict[int, Any] = {}
            for slot_idx in range(inv._max_slots):
                iid = inv.get_item_instance_id_by_slot(SlotId(slot_idx))
                if iid is None:
                    continue
                item = runtime._item_repo.find_by_id(iid)
                if item is None:
                    continue
                sid = item.item_spec.item_spec_id.value
                counts[sid] = counts.get(sid, 0) + 1
                if sid not in specs:
                    specs[sid] = item.item_spec
            for sid, spec in specs.items():
                spec_str = _safe_get_str(runtime.id_mapper, "item_spec", sid)
                items.append(InventoryItemResponse(
                    item_spec_id=spec_str,
                    name=spec.name,
                    description=spec.description,
                    quantity=counts[sid],
                ))

        return InventoryResponse(character_id=character_id, items=items)

    # ── Chat (stub) ──

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

    # ── Results (stub) ──

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

    # ── Saves (stub) ──

    def list_saves(self) -> SaveListResponse:
        return SaveListResponse()

    def save_session(self, session_id: str) -> Optional[SaveSlotResponse]:
        return None

    def load_save(self, save_id: str) -> Optional[SaveSlotResponse]:
        return None
