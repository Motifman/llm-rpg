"""Central manager that bridges FastAPI routers with the game runtime.

Wires ``WorldRuntime`` / scenario loaders / session lifecycle to
the API layer.  Methods that are not yet backed by real logic return
stub data so that the full API surface remains exercisable.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from ai_rpg_world.application.intent.action_failed_observation_emitter import (
    ActionFailedObservationEmitter,
)
from ai_rpg_world.application.intent.intent_id_generator import (
    IntentIdGenerator,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILLMPlayerResolver
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.llm.services.world_llm_prompt import (
    CharacterPromptInput,
)
from ai_rpg_world.application.llm.wiring._llm_client_factory import (
    create_llm_client_from_config,
)
from ai_rpg_world.application.observation.services.heartbeat_observation_emitter import (
    HeartbeatObservationEmitter,
)
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.application.inventory.services.player_inventory_query_service import (
    PlayerInventoryQueryService,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMappingError
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

from ai_rpg_world.application.llm.services.failure_helpers import (  # noqa: E402
    list_destination_labels as _list_destination_labels,
    list_object_labels as _list_object_labels,
    list_player_labels as _list_player_labels,
    list_targets_of_kind as _list_targets_of_kind,
)
from ai_rpg_world.application.llm.services.world_llm_turn.escape_tools import (  # noqa: E402
    ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS,
    ToolHandlerConsistencyError,
    filter_definitions_for_escape_llm,
    validate_tool_handler_consistency,
)
from ai_rpg_world.application.llm.services.world_llm_turn.metrics_sink import (  # noqa: E402
    LlmMetricsTraceSink as _LlmMetricsTraceSink,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_name_rescue import (  # noqa: E402
    build_unsupported_tool_message,
    suggest_closest_tool_name,
)
from ai_rpg_world.application.llm.services.world_llm_turn.turn_trigger import (  # noqa: E402
    WorldLlmTurnTrigger as _WorldLlmTurnTrigger,
)
from ai_rpg_world.application.llm.services.world_llm_turn.types import (  # noqa: E402
    LlmPhaseAResult as _LlmPhaseAResult,
)
from ai_rpg_world.application.llm.services.world_llm_turn.wiring import (  # noqa: E402
    WorldLlmWiring as _WorldLlmWiring,
)

def _character_to_prompt_input(
    character: Optional[CharacterDetailResponse],
) -> Optional[CharacterPromptInput]:
    if character is None:
        return None
    return CharacterPromptInput(
        character_id=character.id,
        name=character.name,
        first_person=character.first_person or "私",
        personality_tags=tuple(character.personality_tags or ()),
        appearance=character.appearance or "",
        speech_samples=tuple(character.speech_samples or ()),
        fragmented_memory=character.fragmented_memory or "",
        values=character.values or "",
        strengths=character.strengths or "",
        weaknesses=character.weaknesses or "",
        interpersonal_tendency=character.interpersonal_tendency or "",
        behavioral_rules=tuple(character.behavioral_rules or ()),
    )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
@dataclass
class _WorldSpawnAllPlayersLlmResolver(ILLMPlayerResolver):
    """スポーンした全員をプレゼン層脱出セッションでは LLM ターン対象とみなす。"""

    spawn_player_ids: frozenset[int]

    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        return player_id.value in self.spawn_player_ids
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
class _QueuedTurnTrigger:
    """Minimal turn scheduler used until the API runtime is wired to real LLM turns."""

    pending_player_ids: set[int] = field(default_factory=set)

    def schedule_turn(self, player_id: PlayerId) -> None:
        self.pending_player_ids.add(player_id.value)

    def run_scheduled_turns(self) -> None:
        self.pending_player_ids.clear()
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
    llm_wiring: Any = field(default=None, repr=False)
    pending_llm_turns: set[int] = field(default_factory=set, repr=False)


@dataclass
class GameRuntimeManager:
    """Facade consumed by all API routers."""

    scenarios_dir: Path = field(default_factory=lambda: Path("data/scenarios"))
    characters_path: Path = field(default_factory=lambda: Path("var/characters.json"))
    runtime_config: Optional[Any] = field(default=None, repr=False)

    _scenario_cache: Dict[str, Dict[str, Any]] = field(
        default_factory=dict, repr=False
    )
    _characters: Dict[str, CharacterDetailResponse] = field(
        default_factory=dict, repr=False
    )
    _characters_loaded: bool = field(default=False, repr=False)
    _sessions: Dict[str, _SessionState] = field(
        default_factory=dict, repr=False
    )
    _chat_histories: Dict[str, list[ChatMessageResponse]] = field(
        default_factory=dict, repr=False
    )
    # 長走時の保険:
    # - tick thread と chat 送信 thread が同時に dict を触る (compound op race)
    # - 履歴に上限なしで永遠に append されてメモリが膨らむ
    # の 2 つを 1 つの lock + cap で潰す。200 件はキャラとの最近の会話を
    # 復元するのに十分で、それ以上は viewer 側で必要なら別 store に永続化
    # する設計を想定。
    _chat_history_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False
    )
    _CHAT_HISTORY_MAX_PER_KEY: int = 200

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

    # ── Characters ──

    def _load_characters(self) -> None:
        if self._characters_loaded:
            return
        self._characters_loaded = True
        if not self.characters_path.exists():
            self._characters = {}
            return
        try:
            with open(self.characters_path, encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read characters %s: %s", self.characters_path, exc)
            self._characters = {}
            return

        entries = raw.get("characters", []) if isinstance(raw, dict) else []
        characters: dict[str, CharacterDetailResponse] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                character = CharacterDetailResponse(**entry)
            except Exception as exc:
                logger.warning("Skipping invalid character entry: %s", exc)
                continue
            characters[character.id] = character
        self._characters = characters

    def _save_characters(self) -> None:
        self.characters_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "characters": [
                character.model_dump()
                for character in sorted(
                    self._characters.values(), key=lambda c: c.name
                )
            ]
        }
        tmp_path = self.characters_path.with_suffix(self.characters_path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp_path.replace(self.characters_path)

    def list_characters(self) -> list[CharacterSummaryResponse]:
        self._load_characters()
        return [
            CharacterSummaryResponse(
                id=character.id,
                name=character.name,
                age_image=character.age_image,
                personality_tags=character.personality_tags,
                portrait_url=character.portrait_url,
                icon_url=character.icon_url,
            )
            for character in sorted(self._characters.values(), key=lambda c: c.name)
        ]

    def get_character(self, character_id: str) -> Optional[CharacterDetailResponse]:
        self._load_characters()
        return self._characters.get(character_id)

    def create_character(
        self, request: CharacterCreateRequest
    ) -> CharacterDetailResponse:
        self._load_characters()
        cid = uuid.uuid4().hex[:8]
        while cid in self._characters:
            cid = uuid.uuid4().hex[:8]
        character = CharacterDetailResponse(
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
            behavioral_rules=list(request.behavioral_rules or ()),
        )
        self._characters[cid] = character
        self._save_characters()
        return character

    def update_character(
        self, character_id: str, request: CharacterUpdateRequest
    ) -> Optional[CharacterDetailResponse]:
        self._load_characters()
        current = self._characters.get(character_id)
        if current is None:
            return None
        data = current.model_dump()
        update_data = request.model_dump(exclude_unset=True)
        data.update({key: value for key, value in update_data.items() if value is not None})
        updated = CharacterDetailResponse(**data)
        self._characters[character_id] = updated
        self._save_characters()
        return updated

    # ── Sessions ──

    def create_session(
        self, request: SessionCreateRequest
    ) -> SessionSummaryResponse:
        sid = uuid.uuid4().hex[:12]
        scenario_path = self.scenarios_dir / f"{request.world_id}.json"
        if not scenario_path.exists():
            raise ValueError(f"World not found: {request.world_id}")

        # PR #450: world_runtime は demos/ から application/ に移動済。
        # presentation 層が demos/ を import する旧構造を解消する。
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        world_character = None
        if request.character_ids:
            detail = self.get_character(request.character_ids[0])
            world_character = _character_to_prompt_input(detail)

        runtime = create_world_runtime(
            scenario_path,
            world_character=world_character,
            config=self.runtime_config,
        )
        spawn_ids = frozenset(int(sp.player_id) for sp in runtime.scenario.player_spawns)
        llm_resolver = _WorldSpawnAllPlayersLlmResolver(spawn_player_ids=spawn_ids)
        # appender / turn_scheduler は heartbeat と ActionFailed の両方で
        # 共有する (同じ observation buffer に書き込み、同じ turn trigger を
        # 呼ぶため)。
        appender = ObservationAppender(runtime._obs_buffer)
        # 注意: llm_wiring を構築する前に turn_scheduler を作る必要がある
        # ため、最初に空の wiring を作り、それから scheduler / emitter を
        # 組み立てて wiring に注入する流れにする。
        llm_wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=create_llm_client_from_config(runtime._runtime_config),
            llm_session_run_id=sid,
            llm_session_world_id=request.world_id,
        )
        turn_scheduler = ObservationTurnScheduler(
            turn_trigger=llm_wiring.llm_turn_trigger,
            llm_player_resolver=llm_resolver,
        )

        def _heartbeat_llm_player_ids() -> Iterable[PlayerId]:
            return tuple(PlayerId(int(sp.player_id)) for sp in runtime.scenario.player_spawns)

        def _is_traveling(pid: PlayerId) -> bool:
            """#404 fix: 移動中の player に heartbeat を打たない判定。

            heartbeat 観測は ``schedules_turn=True`` なので、移動中に届くと
            「移動中なのに何かしようとして失敗」する空回りターンを誘発する。
            travel_stage が arrival 時に schedule_turn を打つので、移動中は
            完全に silent にしてよい。
            """
            try:
                status = runtime._player_status_repo.find_by_id(pid)
            except Exception:
                return False
            if status is None:
                return False
            nav = status.spot_navigation_state
            return nav is not None and nav.is_traveling

        heartbeat_emitter = HeartbeatObservationEmitter(
            appender,
            turn_scheduler,
            _heartbeat_llm_player_ids,
            time_label_provider=lambda _tick: llm_wiring._time_label(),
            interval_ticks=int(
                getattr(runtime._runtime_config, "llm_idle_timeout_ticks", 6)
            ),
            is_traveling_provider=_is_traveling,
        )
        # ActionFailed 観測の wire: 失敗 DTO を当該プレイヤーへの観測に変換する。
        # ``intent_id_generator`` は wiring と emitter で共有しないが、wiring 側
        # で intent_id を払い出して emitter に渡す形を取る (emitter は受け取った
        # intent をそのまま使う最小役割)。
        action_failed_emitter = ActionFailedObservationEmitter(
            observation_appender=appender,
            turn_scheduler=turn_scheduler,
            time_label_provider=llm_wiring._time_label,
        )
        llm_wiring.attach_action_failed_wiring(
            emitter=action_failed_emitter,
            generator=IntentIdGenerator(),
        )
        runtime.set_simulation_llm_turn_trigger(llm_wiring.llm_turn_trigger)
        runtime.set_simulation_heartbeat_emitter(heartbeat_emitter)
        # PR 2 (#227): speech 配信は ObservationPipeline 経由になった。受信者が
        # 他者発話を聞いた場合、ObservationTurnScheduler 経由でターンを積む
        # 必要があるため、wiring 完成後の scheduler を runtime に注入する。
        runtime.set_observation_turn_scheduler(turn_scheduler)
        # #404 fix: travel 到着時に LLM ターンを再開させるためのコールバックを
        # travel_stage に注入する。is_traveling フィルタで sleep していた player
        # は、ここで schedule_turn → 次の post-tick hook で run_turn される。
        travel_stage = getattr(runtime, "_travel_stage", None)
        if travel_stage is not None and hasattr(travel_stage, "set_on_arrival"):
            travel_stage.set_on_arrival(llm_wiring.llm_turn_trigger.schedule_turn)

        title = runtime.metadata.title
        state = _SessionState(
            session_id=sid,
            world_id=request.world_id,
            world_title=title,
            character_ids=request.character_ids,
            status="running",
            created_at=_utcnow_iso(),
            runtime=runtime,
            llm_wiring=llm_wiring,
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
        # 1 tick = 5 分 の旧仮定を廃止。runtime の正規 _time_label に委譲する
        # (day_night サイクルから派生した正しい時刻を返す)。
        tick = runtime.current_tick() if runtime else 0
        runtime_label_fn = getattr(runtime, "_time_label", None) if runtime else None
        if callable(runtime_label_fn):
            time_label = runtime_label_fn()
        else:
            hours = tick % 24
            time_label = f"{hours}:00"

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

    def iter_running_runtimes(self) -> "Iterator[tuple[str, Any]]":
        """Yield ``(session_id, runtime)`` pairs for sessions in 'running' status.

        Used by the background tick loop to advance game time. Skips
        paused/ended sessions and sessions without a runtime (legacy stubs).

        The runtime is typed as ``Any`` because multiple runtime classes
        (escape game, future spot-graph standalone, etc.) share only the
        informal duck-typed ``advance_tick()`` contract.
        """
        for session_id, state in self._sessions.items():
            if state.status != "running" or state.runtime is None:
                continue
            yield session_id, state.runtime

    def run_scheduled_llm_turns(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None or state.llm_wiring is None:
            return False
        turn_trigger = getattr(state.llm_wiring, "llm_turn_trigger", None)
        if turn_trigger is None or not callable(getattr(turn_trigger, "run_scheduled_turns", None)):
            return False
        turn_trigger.run_scheduled_turns()
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
                is_passable=conn.passage.traversable,
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
        pid_int = runtime.id_mapper.get_int("player", character_id)
        pid = PlayerId(pid_int)
        query = PlayerInventoryQueryService(
            player_inventory_repository=runtime._player_inventory_repo,
            item_repository=runtime._item_repo,
        )
        view = query.list_held_items(pid)
        items = [
            InventoryItemResponse(
                item_spec_id=_safe_get_str(
                    runtime.id_mapper, "item_spec", row.item_spec_id
                ),
                name=row.name,
                description=row.description,
                quantity=row.quantity,
            )
            for row in view.items
        ]
        return InventoryResponse(character_id=character_id, items=items)

    # ── Chat (stub) ──

    def send_chat_message(
        self, request: ChatSendRequest
    ) -> ChatMessageResponse:
        if request.scope != "individual":
            raise ValueError("Only individual chat scope is currently supported")

        state = self._sessions.get(request.session_id)
        if state is None:
            raise ValueError(f"Session not found: {request.session_id}")
        if state.runtime is None:
            raise ValueError(f"Session has no active runtime: {request.session_id}")

        runtime = state.runtime

        try:
            target_player_int = runtime.id_mapper.get_int(
                "player", request.target_character_id
            )
        except (ScenarioIdMappingError, KeyError):
            try:
                character_index = state.character_ids.index(request.target_character_id)
                target_player_int = runtime.get_player_ids()[character_index].value
            except (ValueError, IndexError) as exc:
                raise ValueError(
                    f"Character not found in session: {request.target_character_id}"
                ) from exc

        target_player_id = PlayerId(target_player_int)
        now = datetime.now(timezone.utc)
        # 1 tick = 5 分 の旧仮定を廃止。runtime の正規 _time_label に委譲する
        # (day_night サイクルから派生した正しい時刻を返す)。
        tick = runtime.current_tick() if callable(getattr(runtime, "current_tick", None)) else 0
        runtime_label_fn = getattr(runtime, "_time_label", None)
        if callable(runtime_label_fn):
            time_label = runtime_label_fn()
        else:
            hours = tick % 24
            time_label = f"深夜 {hours}:00" if hours < 6 else f"{hours}:00"

        output = ObservationOutput(
            prose=f"どこからか、あなたに向けた声が届いた: 「{request.message}」",
            structured={
                "type": "user_directed_speech",
                "speaker": "user",
                "target_character_id": request.target_character_id,
                "content": request.message,
                "channel": "direct",
            },
            observation_category="social",
            schedules_turn=True,
            breaks_movement=False,
        )

        appender = getattr(state.llm_wiring, "observation_appender", None)
        if appender is None:
            buffer = getattr(runtime, "_obs_buffer", None)
            if buffer is None:
                raise ValueError("Session runtime does not expose an observation buffer")
            appender = ObservationAppender(buffer)
        appender.append(target_player_id, output, now, time_label)

        turn_trigger = getattr(state.llm_wiring, "llm_turn_trigger", None)
        if turn_trigger is not None:
            turn_trigger.schedule_turn(target_player_id)
        else:
            state.pending_llm_turns.add(target_player_id.value)

        message = ChatMessageResponse(
            sender="player",
            message=request.message,
            timestamp=_utcnow_iso(),
            is_player=True,
        )
        key = f"{request.session_id}:{request.target_character_id}"
        # setdefault + append は GIL-atomic でないので、tick thread 側からの
        # 読み出しと competing しないよう lock 内で実行する。
        # ついでに上限超過分を捨てる。
        with self._chat_history_lock:
            for k in (key, request.target_character_id):
                bucket = self._chat_histories.setdefault(k, [])
                bucket.append(message)
                if len(bucket) > self._CHAT_HISTORY_MAX_PER_KEY:
                    # 古い方から削る
                    del bucket[: len(bucket) - self._CHAT_HISTORY_MAX_PER_KEY]
        return message

    def get_chat_history(
        self, character_id: str
    ) -> Optional[ChatHistoryResponse]:
        with self._chat_history_lock:
            return ChatHistoryResponse(
                messages=list(self._chat_histories.get(character_id, []))
            )

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
