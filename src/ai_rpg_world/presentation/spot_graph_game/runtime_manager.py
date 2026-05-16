"""Central manager that bridges FastAPI routers with the game runtime.

Wires ``EscapeGameRuntime`` / scenario loaders / session lifecycle to
the API layer.  Methods that are not yet backed by real logic return
stub data so that the full API surface remains exercisable.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    with_inner_thought_empty_warning,
)
from ai_rpg_world.application.llm.services.escape_llm_prompt import (
    EscapeCharacterPromptInput,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
)
from ai_rpg_world.application.llm.wiring._llm_client_factory import (
    create_llm_client_from_env,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
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


def _character_to_escape_prompt_input(
    character: Optional[CharacterDetailResponse],
) -> Optional[EscapeCharacterPromptInput]:
    if character is None:
        return None
    return EscapeCharacterPromptInput(
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
class _EscapeGameLlmTurnTrigger:
    """Queues escape-game LLM turns and runs them against the session runtime."""

    wiring: "_EscapeGameLlmWiring"
    max_turns: int = 5
    pending_player_ids: set[int] = field(default_factory=set)
    _turn_counts: dict[int, int] = field(default_factory=dict)

    def schedule_turn(self, player_id: PlayerId) -> None:
        self.pending_player_ids.add(player_id.value)
        self._turn_counts[player_id.value] = 0

    def run_scheduled_turns(self) -> None:
        to_run = list(self.pending_player_ids)
        self.pending_player_ids.clear()
        for player_id_value in to_run:
            result = self.wiring.run_turn(PlayerId(player_id_value))
            current_count = self._turn_counts.get(player_id_value, 0) + 1
            if result.was_no_op:
                self._turn_counts.pop(player_id_value, None)
            elif result.should_reschedule or current_count < self.max_turns:
                self.pending_player_ids.add(player_id_value)
                self._turn_counts[player_id_value] = current_count
            else:
                self._turn_counts.pop(player_id_value, None)


@dataclass
class _EscapeGameLlmWiring:
    """Session-local LLM loop for the escape-game runtime."""

    runtime: Any
    observation_buffer: Any
    llm_client: Any = field(default_factory=create_llm_client_from_env)
    max_turns: int = 5

    def __post_init__(self) -> None:
        self.observation_appender = ObservationAppender(self.observation_buffer)
        self.llm_turn_trigger = _EscapeGameLlmTurnTrigger(
            wiring=self,
            max_turns=self.max_turns,
        )

    def run_turn(self, player_id: PlayerId) -> LlmCommandResultDto:
        prompt = self.runtime.build_full_prompt(player_id)
        messages = [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters,
                },
            }
            for definition in self.runtime.get_tool_definitions()
        ]
        tool_call = self.llm_client.invoke(messages, tools, "required")
        if tool_call is None:
            result = LlmCommandResultDto(
                success=False,
                message="LLM がツールを返しませんでした。",
                error_code="NO_TOOL_CALL",
                remediation="必ずいずれか 1 つのツールを呼び出してください。",
                should_reschedule=False,
                was_no_op=True,
            )
            self.runtime._record_action_result(
                player_id,
                "LLM API 呼び出し",
                result.message,
            )
            return result

        name = str(tool_call.get("name", ""))
        arguments = self._coerce_arguments(tool_call.get("arguments"))
        try:
            result = self._execute_tool(
                player_id,
                name,
                arguments,
                prompt["tool_runtime_context"],
            )
        except Exception as exc:
            result = LlmCommandResultDto(
                success=False,
                message=f"LLM ツール実行に失敗しました: {exc}",
                error_code="LLM_TOOL_EXECUTION_FAILED",
                remediation="現在の状況に表示されたラベルと利用可能な action_name を確認してください。",
            )
        skip_duplicate_action_log = result.success and name in (
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
        )
        if not skip_duplicate_action_log:
            self.runtime._record_action_result(
                player_id,
                f"{name}({json.dumps(arguments, ensure_ascii=False)})",
                result.message,
            )
        return result

    def _coerce_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if isinstance(raw_arguments, str) and raw_arguments:
            try:
                parsed = json.loads(raw_arguments)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _execute_tool(
        self,
        player_id: PlayerId,
        name: str,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        from ai_rpg_world.application.llm.tool_constants import (
            TOOL_NAME_SAY,
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            TOOL_NAME_SPOT_GRAPH_WAIT,
            TOOL_NAME_TODO_ADD,
            TOOL_NAME_TODO_COMPLETE,
            TOOL_NAME_TODO_LIST,
            TOOL_NAME_WHISPER,
        )

        targets = getattr(runtime_context, "targets", {})
        if name == TOOL_NAME_SPOT_GRAPH_EXPLORE:
            result = self.runtime.do_explore(player_id)
            message = (
                "新しい発見はなかった"
                if not result.discovery_descriptions
                else "発見: " + " / ".join(result.discovery_descriptions)
            )
            return with_inner_thought_empty_warning(
                name, arguments, LlmCommandResultDto(success=True, message=message)
            )

        if name == TOOL_NAME_SPOT_GRAPH_TRAVEL_TO:
            label = str(arguments.get("destination_label", ""))
            target = targets.get(label)
            if target is None or target.spot_id is None:
                return LlmCommandResultDto(
                    success=False,
                    message=f"移動先ラベルが見つかりません: {label}",
                    error_code="INVALID_DESTINATION_LABEL",
                    remediation="現在の状況に表示された接続先ラベルを指定してください。",
                )
            destination_id = self.runtime.id_mapper.get_str("spot", target.spot_id)
            self.runtime.do_move(player_id, destination_id)
            return with_inner_thought_empty_warning(
                name,
                arguments,
                LlmCommandResultDto(
                    success=True,
                    message=f"{target.display_name}へ移動しました。",
                ),
            )

        if name == TOOL_NAME_SPOT_GRAPH_INTERACT:
            label = str(arguments.get("object_label", ""))
            action_name = str(arguments.get("action_name", ""))
            target = targets.get(label)
            if target is None or target.world_object_id is None:
                return LlmCommandResultDto(
                    success=False,
                    message=f"オブジェクトラベルが見つかりません: {label}",
                    error_code="INVALID_TARGET_LABEL",
                    remediation="現在の状況に表示されたオブジェクトラベルを指定してください。",
                )
            object_id = self.runtime.id_mapper.get_str("object", target.world_object_id)
            result = self.runtime.do_interact(player_id, object_id, action_name)
            return with_inner_thought_empty_warning(
                name,
                arguments,
                LlmCommandResultDto(
                    success=True,
                    message="; ".join(result.messages) if result.messages else "完了",
                ),
            )

        if name == TOOL_NAME_SPOT_GRAPH_WAIT:
            reason = str(arguments.get("reason", "")).strip()
            tick = self.runtime.do_wait(player_id, reason=reason)
            suffix = f"（理由: {reason}）" if reason else ""
            return with_inner_thought_empty_warning(
                name,
                arguments,
                LlmCommandResultDto(
                    success=True,
                    message=f"待機して時間が進んだ: tick={tick}{suffix}",
                ),
            )

        if name == TOOL_NAME_SAY:
            content = str(arguments.get("content", "")).strip()
            if not content:
                return LlmCommandResultDto(
                    success=False,
                    message="発言内容が空です。",
                    error_code="INVALID_SPEECH_CONTENT",
                )
            self._append_agent_speech(player_id, content)
            return LlmCommandResultDto(success=True, message=f"発言した: {content}")

        if name == TOOL_NAME_WHISPER:
            content = str(arguments.get("content", "")).strip()
            target_label = str(arguments.get("target_label", ""))
            target = targets.get(target_label)
            if not content or target is None or target.player_id is None:
                return LlmCommandResultDto(
                    success=False,
                    message="囁きの宛先または内容が不正です。",
                    error_code="INVALID_WHISPER",
                )
            self._append_agent_speech(
                player_id,
                content,
                target_player_id=PlayerId(target.player_id),
            )
            return LlmCommandResultDto(success=True, message=f"囁いた: {content}")

        if name == TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION:
            return LlmCommandResultDto(
                success=False,
                message="サブロケーション変更は脱出ランタイムでは未対応です。",
                error_code="UNSUPPORTED_TOOL",
            )

        if name in (
            TOOL_NAME_TODO_ADD,
            TOOL_NAME_TODO_LIST,
            TOOL_NAME_TODO_COMPLETE,
        ):
            return self.runtime.run_llm_auxiliary_tool(player_id, name, arguments)

        return LlmCommandResultDto(
            success=False,
            message=f"未対応のツールです: {name}",
            error_code="UNSUPPORTED_TOOL",
        )

    def _append_agent_speech(
        self,
        speaker_player_id: PlayerId,
        content: str,
        target_player_id: Optional[PlayerId] = None,
    ) -> None:
        speaker_name = self.runtime.get_player_name(speaker_player_id)
        recipients = [target_player_id] if target_player_id is not None else self.runtime.get_player_ids()
        for recipient in recipients:
            if recipient is None:
                continue
            is_self = recipient.value == speaker_player_id.value
            prose = (
                f"あなたは言った: 「{content}」"
                if is_self
                else f"{speaker_name}が言った: 「{content}」"
            )
            self.observation_appender.append(
                recipient,
                ObservationOutput(
                    prose=prose,
                    structured={
                        "type": "player_spoke",
                        "speaker": speaker_name,
                        "speaker_player_id": speaker_player_id.value,
                        "content": content,
                        "channel": "say" if target_player_id is None else "whisper",
                        "role": "self" if is_self else "other",
                    },
                    observation_category="self_only" if is_self else "social",
                    schedules_turn=not is_self,
                ),
                datetime.now(timezone.utc),
                self._time_label(),
            )
            if not is_self:
                self.llm_turn_trigger.schedule_turn(recipient)

    def _time_label(self) -> str:
        tick = self.runtime.current_tick()
        hours = (tick * 5) % (24 * 60)
        h, m = divmod(hours, 60)
        return f"深夜 {h}:{m:02d}" if h < 6 else f"{h}:{m:02d}"


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
    characters_path: Path = field(default_factory=lambda: Path("data/characters.json"))

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
        scenario_path = self.scenarios_dir / f"{request.world_id}.json"
        if not scenario_path.exists():
            raise ValueError(f"World not found: {request.world_id}")

        from demos.escape_game.escape_game_runtime import (
            create_escape_game_runtime,
        )

        escape_character = None
        if request.character_ids:
            detail = self.get_character(request.character_ids[0])
            escape_character = _character_to_escape_prompt_input(detail)

        runtime = create_escape_game_runtime(
            scenario_path, escape_character=escape_character
        )
        llm_wiring = _EscapeGameLlmWiring(runtime=runtime, observation_buffer=runtime._obs_buffer)
        runtime.set_simulation_llm_turn_trigger(llm_wiring.llm_turn_trigger)

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
        tick = runtime.current_tick() if callable(getattr(runtime, "current_tick", None)) else 0
        hours = (tick * 5) % (24 * 60)
        h, m = divmod(hours, 60)
        time_label = f"深夜 {h}:{m:02d}" if h < 6 else f"{h}:{m:02d}"

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
        self._chat_histories.setdefault(key, []).append(message)
        self._chat_histories.setdefault(request.target_character_id, []).append(message)
        return message

    def get_chat_history(
        self, character_id: str
    ) -> Optional[ChatHistoryResponse]:
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
