"""Current world_runtime runtime behavior contracts.

These are characterization tests for the runtime path used by
``make experiment`` and the spot_graph_game server. They intentionally capture
today's behavior before further runtime convergence work.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    ToolDefinitionDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.prompt_dataset_capture import (
    PromptDatasetCaptureSink,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_ASSESS_SITUATION,
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
    TOOL_NAME_MEMO_LIST,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _LlmPhaseAResult,
    _WorldLlmWiring,
)

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)
_SCENARIOS_DIR = _SCENARIO_PATH.parent
_FIXTURE_SCENARIOS_DIR = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "scenarios"
)


@pytest.fixture()
def clean_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep these contract tests independent from the caller's shell env."""
    for key in (
        "LLM_EPISODIC_ENABLED",
        "LLM_EPISODIC_SUBJECTIVE_ENABLED",
        "SEMANTIC_PASSIVE_TOP_K",
        "SEMANTIC_LLM_GIST_ENABLED",
        "SHORT_TERM_MEMORY_KIND",
        "MEMO_TOOLS_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)


def _create_runtime(
    config: ResolvedLlmRuntimeConfig | None = None,
    *,
    scenario_path: Path = _SCENARIO_PATH,
    include_todo_tools: bool = True,
):
    from ai_rpg_world.application.world_runtime.world_runtime import (
        create_world_runtime,
    )

    return create_world_runtime(
        scenario_path,
        config=config or ResolvedLlmRuntimeConfig.for_tests(),
        include_todo_tools=include_todo_tools,
    )


def _user_prompt_text(prompt: dict) -> str:
    return "\n".join(
        m.get("content", "")
        for m in prompt.get("messages", [])
        if m.get("role") == "user"
    )


def _system_prompt_text(prompt: dict) -> str:
    return "\n".join(
        m.get("content", "")
        for m in prompt.get("messages", [])
        if m.get("role") == "system"
    )


def _seed_semantic_learning(runtime, player_id, text: str) -> None:
    stack = runtime._episodic_stack
    being = runtime.aux_being_resolver.resolve_being_id(
        runtime._aux_being_default_world_id, player_id
    )
    assert being is not None
    assert stack.semantic_memory_store is not None
    stack.semantic_memory_store.add_by_being(
        being,
        SemanticMemoryEntry(
            entry_id="contract-semantic-entry",
            player_id=int(player_id.value),
            being_id=being,
            text=text,
            evidence_episode_ids=("contract-episode",),
            confidence=0.8,
            created_at=datetime.now(timezone.utc),
            importance_score=8,
            tags=("contract",),
        ),
    )


class _PromotionSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[int, BeingId]] = []

    def on_after_tool_turn(self, player_id: int, being_id: BeingId) -> None:
        self.calls.append((player_id, being_id))


class _OrderedActionStoreSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.kwargs: dict = {}

    def append(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
        **kwargs,
    ) -> None:
        self.events.append("append")
        self.kwargs = {
            "player_id": player_id,
            "action_summary": action_summary,
            "result_summary": result_summary,
            **kwargs,
        }


class _OrderedChunkCoordinatorSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[PlayerId] = []

    def after_action_recorded(self, player_id: PlayerId, being_id: BeingId) -> None:
        self.events.append("chunk")
        self.calls.append(player_id)


class _OrderedPromotionSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[tuple[int, BeingId]] = []

    def on_after_tool_turn(self, player_id: int, being_id: BeingId) -> None:
        self.events.append("promotion")
        self.calls.append((player_id, being_id))


class _RaisingChunkCoordinatorSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def after_action_recorded(self, player_id: PlayerId, being_id: BeingId) -> None:
        self.events.append("chunk")
        raise RuntimeError("chunk failed")


class _RaisingPromotionSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def on_after_tool_turn(self, player_id: int, being_id: BeingId) -> None:
        self.events.append("promotion")
        raise RuntimeError("promotion failed")


class _LoopGuardSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[tuple[PlayerId, str, dict]] = []
        self.last_kwargs: dict = {}

    def record_and_check(
        self,
        player_id: PlayerId,
        tool_name: str,
        arguments: dict,
        **kwargs,
    ) -> None:
        # PR-AA (Y_after_pr639_640 後続): 新 kwargs (success / error_code)
        # を受け入れる。spy は kwargs もキャプチャする
        # (配線テスト: runtime_manager が success/error_code を正しく
        # 転送しているかの検証用)。
        self.events.append("loop_guard")
        self.calls.append((player_id, tool_name, arguments))
        self.last_kwargs = kwargs


class _ContractRuntime:
    def __init__(self, events: list[str] | None = None) -> None:
        self._obs_buffer = DefaultObservationContextBuffer()
        recent_event_store = UnifiedRecentEventStore()
        self._short_term_memory = DefaultSlidingWindowMemory(
            event_store=recent_event_store
        )
        self._action_result_store = DefaultActionResultStore(
            event_store=recent_event_store
        )
        self.events = events if events is not None else []
        self.action_results: list[dict] = []
        self.trace_recorder = None
        self._runtime_config = ResolvedLlmRuntimeConfig.for_tests()
        self._player_life_query = SimpleNamespace(can_take_turn=lambda player_id: True)

    def build_full_prompt(
        self, player_id: PlayerId, *, action_instruction: str | None = None
    ) -> dict:
        instruction = action_instruction or "user"
        return {
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": instruction},
            ],
            "action_instruction": instruction,
            "tool_runtime_context": ToolRuntimeContextDto.empty(),
        }

    @staticmethod
    def escape_game_action_instruction(tool_names: list[str]) -> str:
        return "tools=" + ",".join(tool_names) + "\n必ずツールを呼ぶ"

    def get_tool_definitions(self, *, player_id=None) -> list[ToolDefinitionDto]:
        """自由時間の runtime が出すツール一式を返す。

        **explore だけを返していたが、それでは現実と食い違う。** この
        contract 試験は travel_to や interact も dispatch するので、
        「出していないツールを dispatch する runtime」を演じていた。

        本物はそんな状態にならないし、実際 dispatch 側に「出していない
        ツールは実行させない」検査を入れたら、この代役だけが引っかかった。
        代役のほうを実態に寄せる。
        """
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            get_spot_graph_specs,
        )

        return [
            ToolDefinitionDto(
                name=defn.name,
                description=defn.description,
                parameters=defn.parameters,
            )
            for defn, _ in get_spot_graph_specs()
        ] + [
            # 試験が _tool_handlers に直接差し込む合成ツール。**ハンドラを
            # 足すなら一覧にも出す**のが実態で、片方だけだと「出していない
            # ツールを dispatch する runtime」という現実に無い状態になる。
            ToolDefinitionDto(
                name=_CONTRACT_PROBE_TOOL,
                description="contract probe",
                parameters={"type": "object", "properties": {}, "required": []},
            )
        ]

    def current_tick(self) -> int:
        return 7

    def advance_memory_turn(self, player_id: PlayerId) -> None:
        return None

    def get_player_ids(self) -> list[PlayerId]:
        return [PlayerId(1)]

    def get_player_name(self, player_id: PlayerId) -> str:
        return "契約テスト用プレイヤー"

    def _record_action_result(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
        *,
        tool_name: str,
        success: bool = True,
        error_code: str | None = None,
        scene_boundary: bool = False,
        inner_thought: str | None = None,
        intention: str | None = None,
        emotion_hint: str | None = None,
        argument_fingerprint: str | None = None,
        identifier_arguments: Mapping[str, str] | None = None,
        free_text_argument_names: tuple[str, ...] = (),
    ) -> None:
        # 実 escape _record_action_result (U2) と同じ subjective kwargs を受ける。
        self.events.extend(["append", "chunk", "promotion"])
        self._action_result_store.append(
            player_id,
            action_summary,
            result_summary,
            success=success,
            error_code=error_code,
            tool_name=tool_name,
            argument_fingerprint=argument_fingerprint,
            inner_thought=inner_thought,
            intention=intention,
            emotion_hint=emotion_hint,
            identifier_arguments=identifier_arguments,
            free_text_argument_names=free_text_argument_names,
        )
        self.action_results.append(
            {
                "player_id": player_id,
                "action_summary": action_summary,
                "result_summary": result_summary,
                "tool_name": tool_name,
                "success": success,
                "error_code": error_code,
                "scene_boundary": scene_boundary,
                "inner_thought": inner_thought,
                "intention": intention,
                "emotion_hint": emotion_hint,
                "identifier_arguments": dict(identifier_arguments or {}),
                "free_text_argument_names": free_text_argument_names,
            }
        )


class _TraceRecorderSpy:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, **kwargs: Any) -> None:
        self.records.append((kind, dict(kwargs)))


class _AuxBeingResolverStub:
    def resolve_being_id(self, world_id: WorldId, player_id: PlayerId) -> BeingId:
        return BeingId(f"being_w{world_id.value}_p{player_id.value}")


class _ReasonFirstRuntime(_ContractRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.reason_first_two_step_enabled = lambda player_id: True
        self.trace_recorder = _TraceRecorderSpy()
        self.tool_schema_modes: list[str] = []

    def get_tool_definitions(
        self, *, tool_schema_mode: str = "legacy", player_id=None
    ) -> list[ToolDefinitionDto]:
        self.tool_schema_modes.append(tool_schema_mode)
        tools = [
            ToolDefinitionDto(
                name=TOOL_NAME_SPOT_GRAPH_EXPLORE,
                description="explore",
                parameters={"type": "object", "properties": {}, "required": []},
            )
        ]
        if tool_schema_mode == "reason_first":
            tools.append(
                ToolDefinitionDto(
                    name=TOOL_NAME_ASSESS_SITUATION,
                    description="assess",
                    parameters={
                        "type": "object",
                        "properties": {
                            "inner_thought": {"type": "string"},
                        },
                        "required": ["inner_thought"],
                    },
                )
            )
        return tools


class _GatedReasonFirstRuntime(_ReasonFirstRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.reason_first_two_step_enabled = True


_SESSION_ID_NOT_PASSED = object()


class _SequencedLlmClient:
    def __init__(self, responses: list[dict | BaseException | None]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def invoke(
        self,
        messages,
        tools,
        tool_choice="required",
        *,
        metrics_sink=None,
        reasoning_effort=None,
        prompt_capture_context=None,
        call_phase="one_step",
        session_id=_SESSION_ID_NOT_PASSED,
    ):
        self.calls.append(
            {
                "messages": copy.deepcopy(messages),
                "tools": copy.deepcopy(tools),
                "tool_choice": copy.deepcopy(tool_choice),
                "reasoning_effort": reasoning_effort,
                "call_phase": call_phase,
                "session_id_present": session_id is not _SESSION_ID_NOT_PASSED,
                "session_id": (
                    None if session_id is _SESSION_ID_NOT_PASSED else session_id
                ),
            }
        )
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if prompt_capture_context is not None:
            prompt_capture_context.sink.record_call(
                context=prompt_capture_context.context,
                request_kwargs={
                    "model": "stub",
                    "messages": copy.deepcopy(messages),
                    "tools": copy.deepcopy(tools),
                    "tool_choice": copy.deepcopy(tool_choice),
                },
                response={
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": response.get("name"),
                                            "arguments": json.dumps(
                                                response.get("arguments", {}),
                                                ensure_ascii=False,
                                            ),
                                        }
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
                output=copy.deepcopy(response),
                metrics={"success": True},
            )
        return copy.deepcopy(response)


def _phase_a(
    player_id: PlayerId,
    *,
    tool_call: dict | None,
    exception: BaseException | None = None,
) -> _LlmPhaseAResult:
    return _LlmPhaseAResult(
        player_id=player_id,
        prompt={
            "messages": [],
            "tool_runtime_context": ToolRuntimeContextDto.empty(),
        },
        tools_payload=[],
        tool_call=tool_call,
        exception=exception,
    )


def _wiring_for_contract_runtime(runtime: _ContractRuntime) -> _WorldLlmWiring:
    return _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient(None),
    )


def _reason_first_wiring(
    runtime: _ReasonFirstRuntime,
    client: _SequencedLlmClient,
) -> _WorldLlmWiring:
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=client,
    )
    return wiring


def test_llm_session_id_is_stable_per_player_and_separates_players_and_runs(
    clean_runtime_env: None,
) -> None:
    """会話 ID は同じ run・世界・player で固定し、player または run が違えば分離する。"""
    runtime = _ReasonFirstRuntime()
    wiring = _reason_first_wiring(runtime, _reason_first_success_client())
    wiring.llm_session_run_id = "run034"
    wiring.llm_session_world_id = "station_drill"

    first = wiring._llm_session_id(PlayerId(1))

    assert wiring._llm_session_id(PlayerId(1)) == first
    assert wiring._llm_session_id(PlayerId(2)) != first
    wiring.llm_session_run_id = "run035"
    assert wiring._llm_session_id(PlayerId(1)) != first


def test_disabled_session_id_is_omitted_from_every_llm_invocation(
    clean_runtime_env: None,
) -> None:
    """設定を無効にすると、空値でなく session_id キーワード自体を送らない。"""
    runtime = _ReasonFirstRuntime()
    runtime._runtime_config = ResolvedLlmRuntimeConfig.for_tests(
        llm_session_id_enabled=False
    )
    client = _reason_first_success_client()
    wiring = _reason_first_wiring(runtime, client)
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = (
        lambda player_id, arguments, runtime_context: LlmCommandResultDto(
            success=True, message="探索した。"
        )
    )

    wiring.run_turn(PlayerId(1))

    assert [call["session_id_present"] for call in client.calls] == [False, False]


def test_reason_first_phases_share_one_player_session_id(
    clean_runtime_env: None,
) -> None:
    """評価段と行動段は同じ player の会話なので、段階を跨いでも同じ ID を送る。"""
    runtime = _ReasonFirstRuntime()
    client = _reason_first_success_client()
    wiring = _reason_first_wiring(runtime, client)
    wiring.llm_session_run_id = "run034"
    wiring.llm_session_world_id = "station_drill"
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = (
        lambda player_id, arguments, runtime_context: LlmCommandResultDto(
            success=True, message="探索した。"
        )
    )

    wiring.run_turn(PlayerId(1))

    assert [call["call_phase"] for call in client.calls] == [
        "assess_phase",
        "action_phase",
    ]
    assert [call["session_id"] for call in client.calls] == [
        "run034:wstation_drill:p1",
        "run034:wstation_drill:p1",
    ]


def test_meeting_transition_keeps_the_same_player_session_id(
    clean_runtime_env: None,
) -> None:
    """会議の入口で会話 ID を作り直さず、自由時間と同じ配信先固定を継続する。"""
    runtime = _create_runtime()
    wiring = _wiring_for_contract_runtime(runtime)
    wiring.llm_session_run_id = "run034"
    wiring.llm_session_world_id = "station_drill"
    player_id = runtime.get_player_ids()[0]
    before_meeting = wiring._llm_session_id(player_id)

    runtime.begin_meeting(initiator_player_id=player_id, trigger="body_report")

    assert wiring._llm_session_id(player_id) == before_meeting


def test_default_world_runtime_prompt_is_spot_graph_and_semantic_free(
    clean_runtime_env: None,
) -> None:
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]

    prompt = runtime.build_full_prompt(player_id)
    user = _user_prompt_text(prompt)
    tool_names = [definition.name for definition in runtime.get_tool_definitions(for_every_player=True)]

    assert "【現在地と周囲】" in user
    assert "【直近の出来事】" in user
    assert "【関連する学び】" not in user
    assert "visible_tile_map" not in user
    assert "current_terrain_type" not in user
    assert "travel_to" in tool_names
    assert runtime._episodic_stack is None


def test_synchronized_action_groups_expose_no_tool_of_their_own(
    clean_runtime_env: None,
) -> None:
    """同期アクショングループを宣言しても専用ツールは出ず、interact が入口になる。"""
    runtime = _create_runtime(
        scenario_path=_FIXTURE_SCENARIOS_DIR / "sync_levers_demo.json"
    )

    tool_names = [definition.name for definition in runtime.get_tool_definitions(for_every_player=True)]

    assert "prepare_action" not in tool_names
    assert TOOL_NAME_SPOT_GRAPH_INTERACT in tool_names


def _tool_by_name(runtime, name: str):
    for definition in runtime.get_tool_definitions(for_every_player=True):
        if definition.name == name:
            return definition
    raise AssertionError(f"tool {name} not found")


def _tool_by_name_from(definitions: list[ToolDefinitionDto], name: str) -> ToolDefinitionDto:
    for definition in definitions:
        if definition.name == name:
            return definition
    raise AssertionError(f"tool {name} not found")


def test_being_provisioning_failure_stops_runtime_creation(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Being の用意に失敗すると、create_world_runtime はどの player かを示す RuntimeError で止まる。

    以前は失敗しても runtime を返した (失うのは episode の記録だけだった)。#1520 で
    誰を知っているかを Being が持つようになり、用意できないと入るときの紹介が落ちて
    【知っている人】が消える。実験の条件が run のどこにも残らないまま変わるので、
    壊れた状態で始めない。"""
    from ai_rpg_world.application.being.being_provisioning_service import (
        BeingProvisioningService,
    )

    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")

    def _boom(self, player_id):
        raise RuntimeError("provision boom")

    monkeypatch.setattr(BeingProvisioningService, "ensure_attached", _boom)

    with pytest.raises(RuntimeError, match="player_id=") as excinfo:
        _create_runtime(ResolvedLlmRuntimeConfig.for_tests(episodic_enabled=True))
    assert "provision boom" in str(excinfo.value.__cause__)


def test_no_tool_or_system_prompt_offers_the_prediction_field(
    clean_runtime_env: None,
) -> None:
    """行動ごとの結果の予想 expected_result は #1631 で消したので、どのツールの schema にも system prompt にも出ない。"""
    runtime = _create_runtime()
    for mode in ("legacy", "reason_first"):
        for definition in runtime.get_tool_definitions(
            tool_schema_mode=mode, for_every_player=True
        ):
            assert "expected_result" not in definition.parameters.get("properties", {}), (
                mode,
                definition.name,
            )
    player_id = runtime.get_player_ids()[0]
    system = "\n".join(
        m.get("content", "")
        for m in runtime.build_full_prompt(player_id).get("messages", [])
        if m.get("role") == "system"
    )
    assert "expected_result" not in system


def test_reason_first_tool_mode_adds_assessment_and_strips_action_subjective_fields(
    clean_runtime_env: None,
) -> None:
    """reason_first toolset だけ assess_situation を足し、行動 tool の主観入力を外す。"""
    runtime = _create_runtime()

    legacy_names = [d.name for d in runtime.get_tool_definitions(for_every_player=True)]
    reason_first_tools = runtime.get_tool_definitions(
        tool_schema_mode="reason_first",
        for_every_player=True,
    )
    reason_first_names = [d.name for d in reason_first_tools]

    assert TOOL_NAME_ASSESS_SITUATION not in legacy_names
    assert TOOL_NAME_ASSESS_SITUATION in reason_first_names
    assert reason_first_names[-1] == TOOL_NAME_ASSESS_SITUATION
    assert reason_first_names[:-1] == legacy_names

    assess = _tool_by_name_from(reason_first_tools, TOOL_NAME_ASSESS_SITUATION)
    assert assess.parameters["required"] == ["inner_thought"]

    explore = _tool_by_name_from(reason_first_tools, TOOL_NAME_SPOT_GRAPH_EXPLORE)
    assert "inner_thought" not in explore.parameters["properties"]
    assert "expected_result" not in explore.parameters["properties"]
    assert "inner_thought" not in explore.parameters.get("required", [])
    assert "expected_result" not in explore.parameters.get("required", [])


def test_reason_first_action_phase_omits_assessment_tool_and_keeps_action_schema(
    clean_runtime_env: None,
) -> None:
    """action_phase は評価 tool を渡さず、行動 tool だけを主観欄なしで渡す。"""
    runtime = _ReasonFirstRuntime()
    client = _reason_first_success_client()
    wiring = _reason_first_wiring(runtime, client)
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = (
        lambda player_id, arguments, runtime_context: LlmCommandResultDto(
            success=True, message="探索した。"
        )
    )

    result = wiring.run_turn(PlayerId(1))

    assert result.success is True
    assess_tools = [
        tool["function"]["name"]
        for tool in client.calls[0]["tools"]
    ]
    action_tools = [
        tool["function"]["name"]
        for tool in client.calls[1]["tools"]
    ]
    legacy_tools = [
        tool["function"]["name"]
        for tool in wiring._build_tools_payload(
            PlayerId(1), tool_schema_mode="legacy"
        )
    ]
    assert TOOL_NAME_ASSESS_SITUATION in assess_tools
    assert assess_tools[-1] == TOOL_NAME_ASSESS_SITUATION
    assert TOOL_NAME_ASSESS_SITUATION not in action_tools
    assert assess_tools[:-1] == action_tools
    assert action_tools == legacy_tools
    action_explore = next(
        tool
        for tool in client.calls[1]["tools"]
        if tool["function"]["name"] == TOOL_NAME_SPOT_GRAPH_EXPLORE
    )
    properties = action_explore["function"]["parameters"].get("properties", {})
    assert "inner_thought" not in properties
    assert "expected_result" not in properties


def _reason_first_success_client() -> _SequencedLlmClient:
    return _SequencedLlmClient(
        [
            {
                "name": TOOL_NAME_ASSESS_SITUATION,
                "arguments": {
                    "inner_thought": "反復失敗を避けて別手を選ぶ。",
                },
            },
            {"name": TOOL_NAME_SPOT_GRAPH_EXPLORE, "arguments": {}},
        ]
    )


def test_reason_first_feature_flag_off_keeps_one_step(
    clean_runtime_env: None,
) -> None:
    """flag OFF では reason-first へ入らず、既存 1段階経路を使う。"""
    runtime = _GatedReasonFirstRuntime()
    runtime.reason_first_two_step_enabled = False
    client = _SequencedLlmClient(
        [{"name": TOOL_NAME_SPOT_GRAPH_EXPLORE, "arguments": {}}]
    )
    wiring = _reason_first_wiring(runtime, client)
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = (
        lambda player_id, arguments, runtime_context: LlmCommandResultDto(
            success=True, message="探索した。"
        )
    )

    result = wiring.run_turn(PlayerId(1))

    assert result.success is True
    assert [call["call_phase"] for call in client.calls] == ["one_step"]


def test_auto_uses_payload_names_and_retries_one_no_tool_call(
    clean_runtime_env: None,
) -> None:
    """auto は実 payload 名を末尾に示し、文章回答なら強い指示で一度だけ再試行する。"""
    runtime = _ContractRuntime()
    runtime._runtime_config = ResolvedLlmRuntimeConfig.for_tests(
        llm_tool_choice="auto",
        llm_reasoning_effort="minimal",
    )
    client = _SequencedLlmClient(
        [None, {"name": TOOL_NAME_SPOT_GRAPH_EXPLORE, "arguments": {}}]
    )
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=client,
    )
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = (
        lambda player_id, arguments, runtime_context: LlmCommandResultDto(
            success=True, message="探索した。"
        )
    )

    result = wiring.run_turn(PlayerId(1))

    assert result.success is True
    assert [call["tool_choice"] for call in client.calls] == ["auto", "auto"]
    first_names = [tool["function"]["name"] for tool in client.calls[0]["tools"]]
    first_user = client.calls[0]["messages"][-1]["content"]
    assert first_user.endswith(
        "tools=" + ",".join(first_names) + "\n必ずツールを呼ぶ"
    )
    assert "必ずツールを呼ぶ" in first_user
    assert client.calls[1]["messages"][-1]["content"].endswith(
        "文章での回答は受け取れません。いま呼べるツールを必ず 1 つ呼び出してください。"
    )


def test_required_no_tool_call_keeps_the_existing_single_attempt(
    clean_runtime_env: None,
) -> None:
    """required の NO_TOOL_CALL は既存どおり再試行せず、そのターンを失敗として記録する。"""
    runtime = _ContractRuntime()
    client = _SequencedLlmClient([None])
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=client,
    )

    result = wiring.run_turn(PlayerId(1))

    assert result.error_code == "NO_TOOL_CALL"
    assert len(client.calls) == 1
    assert client.calls[0]["tool_choice"] == "required"
    assert client.calls[0]["messages"][-1]["content"].endswith("user")


def test_reason_first_feature_flag_on_without_existing_trigger_keeps_one_step(
    clean_runtime_env: None,
) -> None:
    """flag ON だけでは常時2段階にせず、繰り返しの警告と同じ失敗の反復が無ければ1段階のまま。"""
    runtime = _GatedReasonFirstRuntime()
    client = _SequencedLlmClient(
        [{"name": TOOL_NAME_SPOT_GRAPH_EXPLORE, "arguments": {}}]
    )
    wiring = _reason_first_wiring(runtime, client)
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = (
        lambda player_id, arguments, runtime_context: LlmCommandResultDto(
            success=True, message="探索した。"
        )
    )

    result = wiring.run_turn(PlayerId(1))

    assert result.success is True
    assert [call["call_phase"] for call in client.calls] == ["one_step"]


def test_reason_first_gates_on_recent_same_failure_from_action_result_store(
    clean_runtime_env: None,
) -> None:
    """直近2件が同じ失敗なら既存 ActionResultStore だけを読んで reason-first に入る。"""
    runtime = _GatedReasonFirstRuntime()
    player_id = PlayerId(1)
    for _ in range(2):
        runtime._action_result_store.append(
            player_id,
            "drink_water 湧水の口",
            "今は汲めない。",
            success=False,
            error_code="OBJECT_CONDITION_NOT_MET",
            tool_name="drink_water",
            argument_fingerprint='{"target_label":"湧水の口"}',
        )
    client = _reason_first_success_client()
    wiring = _reason_first_wiring(runtime, client)
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = (
        lambda player_id, arguments, runtime_context: LlmCommandResultDto(
            success=True, message="探索した。"
        )
    )

    result = wiring.run_turn(player_id)

    assert result.success is True
    assert [call["call_phase"] for call in client.calls] == [
        "assess_phase",
        "action_phase",
    ]
    started = [
        payload
        for kind, payload in runtime.trace_recorder.records
        if kind == TraceEventKind.REASON_FIRST_STARTED
    ]
    assert started[-1]["gate_reason"] == "recent_same_failure"


def test_reason_first_gates_on_loop_guard_warning_signal_once(
    clean_runtime_env: None,
) -> None:
    """loop_guard が警告を出した直後の1ターンだけ gate signal を消費して2段階に入る。"""
    runtime = _GatedReasonFirstRuntime()
    client = _reason_first_success_client()
    wiring = _reason_first_wiring(runtime, client)
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = (
        lambda player_id, arguments, runtime_context: LlmCommandResultDto(
            success=True, message="探索した。"
        )
    )
    player_id = PlayerId(1)
    for _ in range(4):
        wiring.tool_call_loop_guard.record_and_check(
            player_id,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            {"target_label": "湧水の口"},
        )

    result = wiring.run_turn(player_id)

    assert result.success is True
    assert [call["call_phase"] for call in client.calls] == [
        "assess_phase",
        "action_phase",
    ]
    started = [
        payload
        for kind, payload in runtime.trace_recorder.records
        if kind == TraceEventKind.REASON_FIRST_STARTED
    ]
    assert started[-1]["gate_reason"] == "loop_guard_warning"


def test_reason_first_gated_turn_writes_assess_and_action_phase_prompt_dataset_rows(
    clean_runtime_env: None,
    tmp_path: Path,
) -> None:
    """gated reason-first 発火時は prompt dataset に assess/action の2 phase を保存する。"""
    runtime = _GatedReasonFirstRuntime()
    runtime.aux_being_resolver = _AuxBeingResolverStub()
    runtime.aux_being_default_world_id = WorldId(1)
    client = _reason_first_success_client()
    sink = PromptDatasetCaptureSink(
        run_dir=tmp_path,
        run_id="run-reason-first",
        run_metadata={"profile": "test"},
    )
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=client,
        prompt_dataset_sink=sink,
    )
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = (
        lambda player_id, arguments, runtime_context: LlmCommandResultDto(
            success=True, message="探索した。"
        )
    )
    for _ in range(4):
        wiring.tool_call_loop_guard.record_and_check(
            PlayerId(1),
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            {"target_label": "湧水の口"},
        )

    result = wiring.run_turn(PlayerId(1))

    assert result.success is True
    calls_path = tmp_path / "prompt_dataset" / "calls.jsonl"
    rows = [
        json.loads(line)
        for line in calls_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["phase"] for row in rows] == ["assess_phase", "action_phase"]
    assert rows[0]["request"]["kwargs"]["tool_choice"] == {
        "type": "function",
        "function": {"name": TOOL_NAME_ASSESS_SITUATION},
    }
    assert rows[1]["request"]["kwargs"]["tool_choice"] == "required"
    toolsets = {
        row["toolset_id"]: row
        for row in (
            json.loads(line)
            for line in (tmp_path / "prompt_dataset" / "toolsets.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
    }
    assess_tool_names = [
        tool["function"]["name"]
        for tool in toolsets[rows[0]["request"]["kwargs"]["tools_ref"]]["tools"]
    ]
    action_tool_names = [
        tool["function"]["name"]
        for tool in toolsets[rows[1]["request"]["kwargs"]["tools_ref"]]["tools"]
    ]
    assert TOOL_NAME_ASSESS_SITUATION in assess_tool_names
    assert TOOL_NAME_ASSESS_SITUATION not in action_tool_names


def test_reason_first_two_step_injects_assessment_before_action_execution(
    clean_runtime_env: None,
) -> None:
    """reason_first 有効時は評価 tool を先に強制し、評価内容を行動引数へ内部注入する。"""
    runtime = _ReasonFirstRuntime()
    client = _SequencedLlmClient(
        [
            {
                "name": TOOL_NAME_ASSESS_SITUATION,
                "arguments": {
                    "inner_thought": "水源は一度失敗したので周囲を見直す。",
                },
            },
            {
                "name": TOOL_NAME_SPOT_GRAPH_EXPLORE,
                "arguments": {},
            },
        ]
    )
    wiring = _reason_first_wiring(runtime, client)
    captured_arguments: dict[str, Any] = {}

    def _handler(
        player_id: PlayerId,
        arguments: dict,
        runtime_context,
    ) -> LlmCommandResultDto:
        captured_arguments.update(arguments)
        return LlmCommandResultDto(success=True, message="探索した。")

    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = _handler

    result = wiring.run_turn(PlayerId(1))

    assert result.success is True
    assert [call["call_phase"] for call in client.calls] == [
        "assess_phase",
        "action_phase",
    ]
    assert client.calls[0]["tool_choice"] == {
        "type": "function",
        "function": {"name": TOOL_NAME_ASSESS_SITUATION},
    }
    assert client.calls[1]["tool_choice"] == "required"
    assert TOOL_NAME_ASSESS_SITUATION in {
        tool["function"]["name"] for tool in client.calls[0]["tools"]
    }
    assert TOOL_NAME_ASSESS_SITUATION not in {
        tool["function"]["name"] for tool in client.calls[1]["tools"]
    }
    assert "水源は一度失敗したので周囲を見直す。" in client.calls[1]["messages"][-1]["content"]
    assert "実行する行動 tool を1つ選ぶ" in client.calls[1]["messages"][-1]["content"]
    assert captured_arguments["inner_thought"] == "水源は一度失敗したので周囲を見直す。"
    kinds = [kind for kind, _ in runtime.trace_recorder.records]
    assert TraceEventKind.REASON_FIRST_STARTED in kinds
    assert TraceEventKind.REASON_FIRST_ASSESSED in kinds
    assert TraceEventKind.REASON_FIRST_ACTION_SELECTED in kinds
    assert TraceEventKind.REASON_FIRST_ASSESSMENT_INJECTED in kinds
    reason_first_payloads = [
        payload
        for kind, payload in runtime.trace_recorder.records
        if str(kind).startswith("reason_first_")
    ]
    turn_ids = {
        payload.get("reason_first_turn_id")
        for payload in reason_first_payloads
    }
    assert len(turn_ids) == 1
    assert next(iter(turn_ids))


def test_reason_first_step1_retries_once_then_returns_no_op_without_action(
    clean_runtime_env: None,
) -> None:
    """step1 が評価 tool 以外を返し続けたら 1 回だけ再試行し、行動実行へ進まない。"""
    runtime = _ReasonFirstRuntime()
    client = _SequencedLlmClient(
        [
            {"name": TOOL_NAME_SPOT_GRAPH_EXPLORE, "arguments": {}},
            {"name": TOOL_NAME_SPOT_GRAPH_EXPLORE, "arguments": {}},
        ]
    )
    wiring = _reason_first_wiring(runtime, client)
    executed: list[str] = []
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = (
        lambda player_id, arguments, runtime_context: executed.append("executed")
        or LlmCommandResultDto(success=True, message="実行された。")
    )

    result = wiring.run_turn(PlayerId(1))

    assert result.success is False
    assert result.error_code == "REASON_FIRST_STEP_FAILED"
    assert result.was_no_op is True
    assert executed == []
    assert [call["call_phase"] for call in client.calls] == [
        "assess_phase",
        "assess_phase",
    ]
    assert len(runtime.action_results) == 1
    assert runtime.action_results[0]["action_summary"] == "迷い"
    assert runtime.action_results[0]["result_summary"] == (
        "何をするか決めきれず、時間が過ぎた。"
    )
    assert runtime.action_results[0]["tool_name"] == "迷い"
    assert runtime.action_results[0]["error_code"] is None
    failed = [
        payload for kind, payload in runtime.trace_recorder.records
        if kind == TraceEventKind.REASON_FIRST_STEP_FAILED
    ]
    assert failed[-1]["phase"] == "assess_phase"
    assert failed[-1]["final"] is True


def test_reason_first_step1_retries_after_invoke_exception_and_continues_to_action(
    clean_runtime_env: None,
) -> None:
    """step1 の一時的な LLM 例外は 1 回だけ再試行し、評価成功後は行動実行へ進む。"""
    runtime = _ReasonFirstRuntime()
    client = _SequencedLlmClient(
        [
            RuntimeError("temporary llm failure"),
            {
                "name": TOOL_NAME_ASSESS_SITUATION,
                "arguments": {
                    "inner_thought": "一度失敗したので状況を見直す。",
                },
            },
            {
                "name": TOOL_NAME_SPOT_GRAPH_EXPLORE,
                "arguments": {},
            },
        ]
    )
    wiring = _reason_first_wiring(runtime, client)
    executed: list[dict[str, Any]] = []

    def _handler(
        player_id: PlayerId,
        arguments: dict,
        runtime_context,
    ) -> LlmCommandResultDto:
        executed.append(dict(arguments))
        return LlmCommandResultDto(success=True, message="探索した。")

    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = _handler

    result = wiring.run_turn(PlayerId(1))
    wiring.llm_turn_trigger._account_result(1, result)

    assert result.success is True
    assert [call["call_phase"] for call in client.calls] == [
        "assess_phase",
        "assess_phase",
        "action_phase",
    ]
    assert runtime._short_term_memory._event_store.completed_turn_count(
        PlayerId(1)
    ) == 1
    assert executed == [
        {
            "inner_thought": "一度失敗したので状況を見直す。",
        }
    ]
    failed = [
        payload for kind, payload in runtime.trace_recorder.records
        if kind == TraceEventKind.REASON_FIRST_STEP_FAILED
    ]
    assert failed[0]["phase"] == "assess_phase"
    assert failed[0]["reason"] == "invoke_exception"
    assert failed[0]["final"] is False
    kinds = [kind for kind, _ in runtime.trace_recorder.records]
    assert TraceEventKind.REASON_FIRST_ASSESSED in kinds
    assert TraceEventKind.REASON_FIRST_ACTION_SELECTED in kinds


def test_reason_first_step1_exception_twice_is_a_failed_call_retried_next_tick(
    clean_runtime_env: None,
) -> None:
    """step1 の呼び出しが 2 回とも例外で落ちたら、呼び出しの失敗 (LLM_API_FAILED) として返し、その人を次の wave の pending に戻す (#1595)。"""
    runtime = _ReasonFirstRuntime()
    client = _SequencedLlmClient(
        [RuntimeError("timed out"), RuntimeError("timed out")]
    )
    wiring = _reason_first_wiring(runtime, client)

    result = wiring.run_turn(PlayerId(1))
    wiring.llm_turn_trigger._account_result(1, result)

    assert result.error_code == "LLM_API_FAILED"
    assert 1 in wiring.llm_turn_trigger.pending_player_ids
    failed = [
        payload for kind, payload in runtime.trace_recorder.records
        if kind == TraceEventKind.REASON_FIRST_STEP_FAILED
    ]
    assert [(f["reason"], f["final"]) for f in failed] == [
        ("invoke_exception", False),
        ("invoke_exception", True),
    ]


def test_reason_first_action_phase_assessment_tool_is_rejected_before_execution(
    clean_runtime_env: None,
) -> None:
    """step2 が誤って評価 tool を返したら不正として止め、評価 tool を実行しない。"""
    runtime = _ReasonFirstRuntime()
    client = _SequencedLlmClient(
        [
            {
                "name": TOOL_NAME_ASSESS_SITUATION,
                "arguments": {
                    "inner_thought": "まず評価する。",
                },
            },
            {
                "name": TOOL_NAME_ASSESS_SITUATION,
                "arguments": {
                    "inner_thought": "まだ評価する。",
                },
            },
        ]
    )
    wiring = _reason_first_wiring(runtime, client)

    result = wiring.run_turn(PlayerId(1))

    assert result.success is False
    assert result.error_code == "REASON_FIRST_ACTION_PHASE_INVALID_TOOL"
    assert result.was_no_op is True
    assert len(client.calls) == 2
    assert client.calls[1]["call_phase"] == "action_phase"
    assert len(runtime.action_results) == 1
    assert runtime.action_results[0]["action_summary"] == "迷い"
    assert runtime.action_results[0]["result_summary"] == (
        "何をするか決めきれず、時間が過ぎた。"
    )
    assert runtime.action_results[0]["tool_name"] == "迷い"
    assert runtime.action_results[0]["error_code"] is None
    failed = [
        payload for kind, payload in runtime.trace_recorder.records
        if kind == TraceEventKind.REASON_FIRST_STEP_FAILED
    ]
    assert failed[-1]["phase"] == "action_phase"
    assert failed[-1]["returned_tool"] == TOOL_NAME_ASSESS_SITUATION
    assert failed[-1]["gate_reason"] == "callable_override"
    assert failed[-1]["action_phase_tool_count"] == 1
    assert failed[-1]["reason_first_turn_id"]


def test_reason_first_action_prompt_places_assessment_before_target_arguments(
    clean_runtime_env: None,
) -> None:
    """reason_first の行動段階の user 文面は、評価・選べる対象引数・最後の指示の順に並び、行動は共有の記録経路で保存される。"""
    runtime = _create_runtime()
    runtime.reason_first_two_step_enabled = lambda player_id: True
    player_id = runtime.get_player_ids()[0]
    client = _SequencedLlmClient(
        [
            {
                "name": TOOL_NAME_ASSESS_SITUATION,
                "arguments": {
                    "inner_thought": "周囲を見れば出口の手がかりが増える。",
                },
            },
            {"name": TOOL_NAME_SPOT_GRAPH_EXPLORE, "arguments": {}},
        ]
    )
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=client,
    )

    result = wiring.run_turn(player_id)

    assert result.success is True
    entry = runtime._action_result_store.get_recent(player_id, 1)[0]
    assert entry.tool_name == TOOL_NAME_SPOT_GRAPH_EXPLORE
    assert [call["call_phase"] for call in client.calls] == [
        "assess_phase",
        "action_phase",
    ]
    assess_user = client.calls[0]["messages"][-1]["content"]
    action_user = client.calls[1]["messages"][-1]["content"]
    assert "【現在選べる対象引数】" not in assess_user
    assert "【現在選べる対象引数】" in action_user
    final_instruction = (
        "- 上の評価を踏まえ、実行する行動 tool を1つ選ぶ。"
        "inner_thought は再生成しない。"
    )
    assert action_user.endswith(final_instruction)
    assert action_user.index("【行動前の状況評価】") < action_user.index(
        "【現在選べる対象引数】"
    )
    assert action_user.index("【現在選べる対象引数】") < action_user.index(
        final_instruction
    )


def test_world_runtime_build_full_prompt_uses_shared_default_prompt_builder(
    clean_runtime_env: None,
) -> None:
    from ai_rpg_world.application.llm.services.prompt_builder import (
        DefaultPromptBuilder,
    )

    runtime = _create_runtime()

    builder = runtime._get_or_build_default_prompt_builder()
    assert isinstance(builder, DefaultPromptBuilder)
    assert builder is runtime._get_or_build_default_prompt_builder()


def test_episodic_stack_gate_follows_config_not_env(
    clean_runtime_env: None,
) -> None:
    """#558 MEDIUM-1 後続: env 未設定でも explicit config.episodic_enabled だけで
    stack が立つ。親 gate を env 直読みから config 単一窓口に寄せた回帰テスト。

    clean_runtime_env が LLM_EPISODIC_ENABLED を消すので、env 経路では立たない。
    config だけで立つことが、env と config を別解釈する silent failure の不在を示す。"""
    runtime = _create_runtime(ResolvedLlmRuntimeConfig.for_tests(episodic_enabled=True))
    assert runtime._episodic_stack is not None
    # episodic OFF の config なら立たない (= gate が config を見ている裏付け)
    off = _create_runtime(ResolvedLlmRuntimeConfig.for_tests(episodic_enabled=False))
    assert off._episodic_stack is None


def test_episodic_on_exposes_episode_recall_with_semantic_default_off(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """episodic stack だけを立てると意味記憶の部品は組まれず、行動の道具は出る。"""
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    runtime = _create_runtime(ResolvedLlmRuntimeConfig.for_tests(episodic_enabled=True))

    stack = runtime._episodic_stack
    assert stack is not None
    assert stack.chunk_coordinator is not None
    assert stack.passive_recall is not None
    assert stack.noun_matcher is not None
    assert stack.semantic_passive_recall is None
    assert stack.semantic_passive_top_k == 0
    assert stack.episodic_semantic_promotion is None
    assert stack.semantic_memory_store is None
    assert stack.memory_link_store is None

    tool_names = [definition.name for definition in runtime.get_tool_definitions(for_every_player=True)]
    assert TOOL_NAME_SPOT_GRAPH_EXPLORE in tool_names


def test_memo_tools_default_visible_in_get_tool_definitions(
    clean_runtime_env: None,
) -> None:
    """既定では既存 run 互換で memo_add / memo_list / memo_done を LLM に露出する。"""
    runtime = _create_runtime(ResolvedLlmRuntimeConfig.for_tests())

    tool_names = {definition.name for definition in runtime.get_tool_definitions(for_every_player=True)}

    assert {TOOL_NAME_MEMO_ADD, TOOL_NAME_MEMO_LIST, TOOL_NAME_MEMO_DONE} <= tool_names
    assert TOOL_NAME_SPOT_GRAPH_EXPLORE in tool_names


def test_memo_tools_flag_false_hides_only_memo_tools(
    clean_runtime_env: None,
) -> None:
    """MEMO_TOOLS_ENABLED=false は memo tool だけを隠し、記憶本体と他 tool は残す。"""
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(
            episodic_enabled=True,
            semantic_passive_top_k=3,
            memo_tools_enabled=False,
        )
    )

    tool_names = {definition.name for definition in runtime.get_tool_definitions(for_every_player=True)}

    assert TOOL_NAME_MEMO_ADD not in tool_names
    assert TOOL_NAME_MEMO_LIST not in tool_names
    assert TOOL_NAME_MEMO_DONE not in tool_names
    assert TOOL_NAME_SPOT_GRAPH_EXPLORE in tool_names
    assert runtime._episodic_stack is not None
    assert runtime._episodic_stack.passive_recall is not None
    assert runtime._episodic_stack.semantic_passive_recall is not None


def test_memo_tools_flag_false_hides_active_memo_section_from_prompt(
    clean_runtime_env: None,
) -> None:
    """memo tool 非露出時は未完了 memo section も消し、使えない memo_done へ誘導しない。"""
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(
            episodic_enabled=True,
            memo_tools_enabled=False,
        )
    )
    runtime._wire_auxiliary_tool_stack()
    being_id = runtime.aux_being_resolver.resolve_being_id(
        runtime.aux_being_default_world_id,
        PlayerId(1),
    )
    assert being_id is not None
    runtime._todo_store.add_by_being(being_id, "山頂で狼煙を上げる")

    prompt = runtime.build_full_prompt(PlayerId(1))
    system_text = _system_prompt_text(prompt)
    user_text = _user_prompt_text(prompt)

    assert TOOL_NAME_MEMO_ADD not in system_text
    assert TOOL_NAME_MEMO_LIST not in system_text
    assert TOOL_NAME_MEMO_DONE not in system_text
    assert "【進行中のメモ】" not in user_text
    assert "山頂で狼煙を上げる" not in user_text


def test_memo_tools_flag_false_disables_memo_completion_hint_service(
    clean_runtime_env: None,
) -> None:
    """memo tool 非露出時は memo 完了 hint も作らず、存在しない memo_done を促さない。"""
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(memo_tools_enabled=False)
    )

    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient(None),
    )

    assert wiring.memo_completion_hint_service is None


def test_semantic_config_wires_world_runtime_stack_and_prompt_learning(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEMANTIC config enables stores, links, promotion, and prompt learning."""
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    monkeypatch.delenv("SEMANTIC_PASSIVE_TOP_K", raising=False)
    monkeypatch.delenv("SEMANTIC_LLM_GIST_ENABLED", raising=False)
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(
            episodic_enabled=True,
            semantic_passive_top_k=3,
            semantic_llm_gist_enabled=False,
        )
    )
    player_id = runtime.get_player_ids()[0]
    stack = runtime._episodic_stack

    assert stack is not None
    assert stack.semantic_passive_top_k == 3
    assert stack.semantic_passive_recall is not None
    assert stack.episodic_semantic_promotion is not None
    assert stack.semantic_memory_store is not None
    assert stack.memory_link_store is not None

    _seed_semantic_learning(
        runtime,
        player_id,
        "CONTRACT_SEMANTIC_MARKER: 禁書庫ではノアの沈黙が手がかりになる",
    )
    prompt = runtime.build_full_prompt(player_id)
    user = _user_prompt_text(prompt)

    assert "【関連する学び】" in user
    assert "CONTRACT_SEMANTIC_MARKER" in user


def test_action_result_recording_runs_semantic_promotion_hook_when_enabled(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """world_runtime's action path calls the semantic promotion hook after chunk write."""
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(
            episodic_enabled=True, semantic_passive_top_k=3
        )
    )
    player_id = runtime.get_player_ids()[0]
    spy = _PromotionSpy()
    runtime._episodic_stack = replace(
        runtime._episodic_stack,
        episodic_semantic_promotion=spy,
    )

    runtime._record_action_result(
        player_id,
        "CONTRACT_ACTION: 周囲を確認する",
        "CONTRACT_RESULT: 禁書庫の静けさを確認した",
        tool_name="contract_probe",
    )

    being = runtime.aux_being_resolver.resolve_being_id(
        runtime._aux_being_default_world_id, player_id
    )
    assert being is not None
    assert spy.calls == [(player_id.value, being)]


def test_record_action_result_preserves_escape_hook_order(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """escape runtime records action first, then chunk, then semantic promotion."""
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(
            episodic_enabled=True, semantic_passive_top_k=3
        )
    )
    player_id = runtime.get_player_ids()[0]
    events: list[str] = []
    store = _OrderedActionStoreSpy(events)
    chunk = _OrderedChunkCoordinatorSpy(events)
    promotion = _OrderedPromotionSpy(events)

    runtime._action_result_store = store
    runtime._episodic_stack = replace(
        runtime._episodic_stack,
        chunk_coordinator=chunk,
        episodic_semantic_promotion=promotion,
    )

    runtime._record_action_result(
        player_id,
        "CONTRACT_ACTION: 静けさを確認した",
        "CONTRACT_RESULT: 記録した",
        tool_name="contract_probe",
    )

    assert events == ["append", "chunk", "promotion"]
    # U1: _record_action_result は共有 ActionResultRecorder に委譲し、recorder は
    # 全フィールドを既定値込みで append に渡す。escape が意味的に渡すフィールドが
    # 含まれていることを subset で固定する (完全一致は呼び出し形の過剰指定)。
    assert {
        "player_id",
        "action_summary",
        "result_summary",
        "occurred_at",
        "tool_name",
        "success",
        "error_code",
        "scene_boundary",
        "occurred_tick",
        "game_time_label",
    } <= set(store.kwargs)
    assert store.kwargs["occurred_at"].tzinfo is timezone.utc
    assert store.kwargs["tool_name"] == "contract_probe"
    assert store.kwargs["game_time_label"] == runtime._time_label()
    # escape は当面 subjective fields を渡さない (#553 baseline / U2 で配線)
    assert store.kwargs["intention"] is None
    assert store.kwargs["emotion_hint"] is None
    being = runtime.aux_being_resolver.resolve_being_id(
        runtime._aux_being_default_world_id, player_id
    )
    assert being is not None
    assert chunk.calls == [player_id]
    assert promotion.calls == [(player_id.value, being)]


def test_record_action_result_skips_memory_hooks_when_episodic_stack_absent(
    clean_runtime_env: None,
) -> None:
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]
    events: list[str] = []
    runtime._action_result_store = _OrderedActionStoreSpy(events)
    runtime._episodic_stack = None

    runtime._record_action_result(
        player_id,
        "CONTRACT_ACTION: 待機した",
        "CONTRACT_RESULT: 何も起きなかった",
        tool_name="contract_probe",
    )

    assert events == ["append"]


def test_record_action_result_skips_promotion_when_not_configured(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    runtime = _create_runtime(ResolvedLlmRuntimeConfig.for_tests(episodic_enabled=True))
    player_id = runtime.get_player_ids()[0]
    events: list[str] = []
    runtime._action_result_store = _OrderedActionStoreSpy(events)
    runtime._episodic_stack = replace(
        runtime._episodic_stack,
        chunk_coordinator=_OrderedChunkCoordinatorSpy(events),
        episodic_semantic_promotion=None,
    )

    runtime._record_action_result(
        player_id,
        "CONTRACT_ACTION: 周囲を見た",
        "CONTRACT_RESULT: 記録した",
        tool_name="contract_probe",
    )

    assert events == ["append", "chunk"]


def test_record_action_result_keeps_action_success_when_memory_hooks_fail(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chunk/promotion failures are logged but do not block the action record."""
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(
            episodic_enabled=True, semantic_passive_top_k=3
        )
    )
    player_id = runtime.get_player_ids()[0]
    events: list[str] = []
    runtime._episodic_stack = replace(
        runtime._episodic_stack,
        chunk_coordinator=_RaisingChunkCoordinatorSpy(events),
        episodic_semantic_promotion=_RaisingPromotionSpy(events),
    )

    runtime._record_action_result(
        player_id,
        "CONTRACT_ACTION: 失敗する記憶 hook を通る",
        "CONTRACT_RESULT: action 自体は完了した",
        tool_name="contract_probe",
    )

    assert events == ["chunk", "promotion"]
    entries = runtime._action_result_store.get_recent(player_id, 10)
    assert len(entries) == 1
    assert entries[0].action_summary == "CONTRACT_ACTION: 失敗する記憶 hook を通る"
    assert entries[0].success is True


def test_phase_b_runs_loop_guard_after_escape_recording_hooks(
    clean_runtime_env: None,
) -> None:
    """Phase B keeps escape action-recording hooks before the loop guard."""
    player_id = PlayerId(1)
    events: list[str] = []
    runtime = _ContractRuntime(events)
    wiring = _wiring_for_contract_runtime(runtime)
    wiring.tool_call_loop_guard = _LoopGuardSpy(events)

    def _handler(
        player_id: PlayerId,
        arguments: dict,
        runtime_context,
    ) -> LlmCommandResultDto:
        runtime._record_action_result(
            player_id,
            "DOMAIN_ACTION: 周囲を探索した",
            "DOMAIN_RESULT: 古いメモを見つけた",
            tool_name=TOOL_NAME_SPOT_GRAPH_EXPLORE,
        )
        return LlmCommandResultDto(success=True, message="発見: 古いメモ")

    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = _handler

    result = wiring.run_phase_b(
        _phase_a(
            player_id,
            tool_call={
                "name": TOOL_NAME_SPOT_GRAPH_EXPLORE,
                "arguments": {"inner_thought": "周囲を見る"},
            },
        )
    )

    assert result.success is True
    assert events == ["append", "chunk", "promotion", "loop_guard"]


def test_phase_b_records_tool_trace_payload_in_action_result_trace(
    clean_runtime_env: None,
) -> None:
    """tool が返した trace_payload は runtime_manager 経由の action_result trace に残る。"""
    player_id = PlayerId(1)
    runtime = _ContractRuntime()
    runtime.trace_recorder = _TraceRecorderSpy()
    wiring = _wiring_for_contract_runtime(runtime)

    def _handler(
        player_id: PlayerId,
        arguments: dict,
        runtime_context,
    ) -> LlmCommandResultDto:
        return LlmCommandResultDto(
            success=False,
            message="システムエラーが発生しました。",
            error_code="SYSTEM_ERROR",
            trace_payload={
                "tool_exception_location": "_use_item",
                "tool_exception_stage": "slot_resolution",
                "tool_exception_type": "RuntimeError",
            },
        )

    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = _handler

    wiring.run_phase_b(
        _phase_a(
            player_id,
            tool_call={
                "name": TOOL_NAME_SPOT_GRAPH_EXPLORE,
                "arguments": {"inner_thought": "試す"},
            },
        )
    )

    action_results = [
        payload
        for kind, payload in runtime.trace_recorder.records
        if kind == TraceEventKind.ACTION_RESULT
    ]
    assert len(action_results) == 1
    payload = action_results[0]
    assert payload["tool_exception_stage"] == "slot_resolution"
    assert payload["tool_exception_type"] == "RuntimeError"
    assert payload["tool_trace_payload"] == {
        "tool_exception_location": "_use_item",
        "tool_exception_stage": "slot_resolution",
        "tool_exception_type": "RuntimeError",
    }


def test_phase_b_keeps_action_result_trace_when_tool_trace_payload_uses_reserved_keys(
    clean_runtime_env: None,
) -> None:
    """trace_payload が予約名を含んでも action_result trace 行は消えない。"""
    player_id = PlayerId(1)
    runtime = _ContractRuntime()
    runtime.trace_recorder = _TraceRecorderSpy()
    wiring = _wiring_for_contract_runtime(runtime)

    def _handler(
        player_id: PlayerId,
        arguments: dict,
        runtime_context,
    ) -> LlmCommandResultDto:
        return LlmCommandResultDto(
            success=False,
            message="システムエラーが発生しました。",
            error_code="SYSTEM_ERROR",
            trace_payload={
                "tick": 999,
                "player_id": 999,
                "tool": "payload_tool",
                "success": True,
                "error_code": "PAYLOAD_ERROR",
                "result_summary": "payload summary",
                "tool_exception_stage": "effect_application",
            },
        )

    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = _handler

    wiring.run_phase_b(
        _phase_a(
            player_id,
            tool_call={
                "name": TOOL_NAME_SPOT_GRAPH_EXPLORE,
                "arguments": {"inner_thought": "試す"},
            },
        )
    )

    action_results = [
        payload
        for kind, payload in runtime.trace_recorder.records
        if kind == TraceEventKind.ACTION_RESULT
    ]
    assert len(action_results) == 1
    payload = action_results[0]
    assert payload["tick"] == 7
    assert payload["player_id"] == 1
    assert payload["tool"] == TOOL_NAME_SPOT_GRAPH_EXPLORE
    assert payload["success"] is False
    assert payload["error_code"] == "SYSTEM_ERROR"
    assert payload["result_summary"] == "システムエラーが発生しました。"
    assert "tool_exception_stage" in payload
    assert payload["tool_trace_payload"]["tick"] == 999
    assert payload["tool_trace_payload"]["error_code"] == "PAYLOAD_ERROR"


@pytest.mark.parametrize(
    "tool_name",
    [
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    ],
)
def test_phase_b_preserves_single_domain_action_log_for_successful_core_tools(
    clean_runtime_env: None,
    tool_name: str,
) -> None:
    """Successful core spot-graph tools keep the runtime's natural-language log only."""
    player_id = PlayerId(1)
    runtime = _ContractRuntime()
    wiring = _wiring_for_contract_runtime(runtime)
    domain_summary = f"DOMAIN_ACTION: {tool_name} を自然文で記録した"

    def _handler(
        player_id: PlayerId,
        arguments: dict,
        runtime_context,
    ) -> LlmCommandResultDto:
        runtime._record_action_result(
            player_id,
            domain_summary,
            "DOMAIN_RESULT: 完了した",
            tool_name=tool_name,
        )
        return LlmCommandResultDto(success=True, message="DTO_RESULT: 完了した")

    wiring._tool_handlers[tool_name] = _handler

    result = wiring.run_phase_b(
        _phase_a(
            player_id,
            tool_call={
                "name": tool_name,
                "arguments": {"inner_thought": "行動する"},
            },
        )
    )

    assert result.success is True
    assert [entry["action_summary"] for entry in runtime.action_results] == [
        domain_summary
    ]
    assert not runtime.action_results[0]["action_summary"].startswith(f"{tool_name}(")


@pytest.mark.parametrize(
    (
        "phase_a",
        "expected_action_summary",
        "expected_result_summary",
        "expected_tool_name",
        "expected_error_code",
    ),
    [
        (
            _phase_a(PlayerId(1), tool_call=None),
            "迷い",
            "何をするか決めきれず、時間が過ぎた。",
            "迷い",
            "NO_TOOL_CALL",
        ),
        (
            _phase_a(
                PlayerId(1),
                tool_call=None,
                exception=RuntimeError("litellm.Timeout: network retry failed"),
            ),
            "一瞬の空白",
            "意識が途切れ、この間の自分の行動を思い出せない。",
            "一瞬の空白",
            "LLM_API_FAILED",
        ),
    ],
)
def test_phase_b_records_llm_level_failures_as_failed_action_results(
    clean_runtime_env: None,
    phase_a: _LlmPhaseAResult,
    expected_action_summary: str,
    expected_result_summary: str,
    expected_tool_name: str,
    expected_error_code: str,
) -> None:
    runtime = _ContractRuntime()
    wiring = _wiring_for_contract_runtime(runtime)

    result = wiring.run_phase_b(phase_a)

    assert result.success is False
    assert result.error_code == expected_error_code
    assert len(runtime.action_results) == 1
    entry = runtime.action_results[0]
    assert entry["action_summary"] == expected_action_summary
    assert entry["result_summary"] == expected_result_summary
    assert entry["tool_name"] == expected_tool_name
    assert entry["success"] is False
    assert entry["error_code"] is None


_INFRASTRUCTURE_VOCABULARY = re.compile(
    r"LLM|API|litellm|error_code|tool_name|(?:^|\W)tool=|network|retry|timeout|traceback",
    re.IGNORECASE,
)


def _recent_action_result_lines(user_prompt: str) -> list[str]:
    recent = user_prompt.split("【直近の出来事】", 1)[-1]
    recent = recent.split("\n\n【", 1)[0]
    return [line for line in recent.splitlines() if "[行動]" in line]


def _infrastructure_vocabulary_violations(user_prompt: str) -> list[str]:
    return [
        line
        for line in _recent_action_result_lines(user_prompt)
        if _INFRASTRUCTURE_VOCABULARY.search(line) is not None
    ]


def _assert_recent_action_results_use_world_words(user_prompt: str) -> None:
    """【直近の出来事】の行動結果だけを、世界外の診断語彙から守る。

    ツール定義や最終指示には ``travel_to`` など、モデルがそのまま返す必要のある
    識別子が意図的に含まれる。そのため全文を禁止せず、本人の経験として記憶される
    ``[行動]`` 行だけを検査する。対象が空なら検査器の故障なので失敗させる。
    """

    action_lines = _recent_action_result_lines(user_prompt)
    assert action_lines, "検査対象の行動結果が見つからない"
    assert _infrastructure_vocabulary_violations(user_prompt) == []


def test_api_failure_reaches_the_actual_prompt_only_in_world_words(
    clean_runtime_env: None,
) -> None:
    """API例外後の実プロンプトには空白の事実だけが残り、診断詳細は混ざらない。"""
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]
    wiring = _wiring_for_contract_runtime(runtime)

    result = wiring.run_phase_b(
        _phase_a(
            player_id,
            tool_call=None,
            exception=RuntimeError("litellm.Timeout: network retry failed"),
        )
    )
    user_prompt = _user_prompt_text(runtime.build_full_prompt(player_id))

    assert result.error_code == "LLM_API_FAILED"
    assert result.trace_payload == {
        "technical_error_detail": "litellm.Timeout: network retry failed"
    }
    _assert_recent_action_results_use_world_words(user_prompt)
    assert "一瞬の空白" in user_prompt
    assert "意識が途切れ、この間の自分の行動を思い出せない。" in user_prompt


def test_world_word_detector_rejects_a_known_bad_infrastructure_result() -> None:
    """既知の旧文面を検出し、対象抽出が空でも陰性試験を通せないようにする。"""
    bad_prompt = (
        "【直近の出来事】\n"
        "- [行動] LLM API 呼び出し → [失敗] | error_code=LLM_API_FAILED | "
        "tool=llm_api_failed | litellm.Timeout: network retry failed\n\n"
        "【現在地と周囲】\n集会室"
    )

    bad_line = bad_prompt.splitlines()[1]
    assert _infrastructure_vocabulary_violations(bad_prompt) == [bad_line]


def test_infrastructure_failure_cue_name_is_also_a_world_word(
    clean_runtime_env: None,
) -> None:
    """本人向け cue の行動名にも旧内部識別子を残さず、世界内の語を使う。"""
    runtime = _ContractRuntime()
    wiring = _wiring_for_contract_runtime(runtime)

    wiring.run_phase_b(
        _phase_a(
            PlayerId(1),
            tool_call=None,
            exception=RuntimeError("litellm.Timeout"),
        )
    )

    assert runtime.action_results[0]["tool_name"] == "一瞬の空白"
    assert _INFRASTRUCTURE_VOCABULARY.search(
        runtime.action_results[0]["tool_name"]
    ) is None


def test_tool_execution_exception_keeps_diagnostics_out_of_the_actual_prompt(
    clean_runtime_env: None,
) -> None:
    """ツール実行例外も本人には空白だけを残し、技術的原因は trace 用 DTO に分離する。"""
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]
    wiring = _wiring_for_contract_runtime(runtime)
    tool_name = TOOL_NAME_SPOT_GRAPH_WAIT

    def _raise_infrastructure_failure(
        player_id: PlayerId,
        arguments: dict,
        runtime_context: ToolRuntimeContextDto,
    ) -> LlmCommandResultDto:
        raise RuntimeError("litellm.ToolCrash: traceback timeout")

    wiring._tool_handlers[tool_name] = _raise_infrastructure_failure
    phase_a = _phase_a(
        player_id,
        tool_call={"name": tool_name, "arguments": {}},
    )
    phase_a.tools_payload = wiring._build_tools_payload(player_id)

    result = wiring.run_phase_b(phase_a)
    user_prompt = _user_prompt_text(runtime.build_full_prompt(player_id))

    assert result.error_code == "LLM_TOOL_EXECUTION_FAILED"
    assert result.message == "行動が形にならないまま、時間が過ぎた。"
    assert result.trace_payload == {
        "technical_error_detail": "litellm.ToolCrash: traceback timeout"
    }
    assert runtime._action_result_store.get_recent(player_id, 1)[0].error_code is None
    _assert_recent_action_results_use_world_words(user_prompt)


def test_api_exception_detail_remains_in_prompt_dataset_only(
    clean_runtime_env: None,
    tmp_path: Path,
) -> None:
    """本人向け結果を世界語にしても、API例外の診断詳細は prompt dataset に保存する。"""
    runtime = _ContractRuntime()
    sink = PromptDatasetCaptureSink(
        run_dir=tmp_path,
        run_id="run-infrastructure-failure",
        run_metadata={"profile": "test"},
    )
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient(None),
        prompt_dataset_sink=sink,
    )
    phase_a = replace(
        _phase_a(
            PlayerId(1),
            tool_call=None,
            exception=RuntimeError("litellm.Timeout: network retry failed"),
        ),
        llm_call_id="call-api-failure",
    )

    wiring.run_phase_b(phase_a)

    rows = [
        json.loads(line)
        for line in (
            tmp_path / "prompt_dataset" / "turn_results.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows[0]["result"] == {
        "action_success": False,
        "action_result_error_code": "LLM_API_FAILED",
        "result_summary": "意識が途切れ、この間の自分の行動を思い出せない。",
        "remediation": "次に意識が戻ったとき、改めて状況を確かめてください。",
        "was_no_op": True,
        "technical_error_detail": "litellm.Timeout: network retry failed",
    }


def test_phase_b_records_unsupported_tool_failure_with_raw_tool_summary(
    clean_runtime_env: None,
) -> None:
    player_id = PlayerId(1)
    runtime = _ContractRuntime()
    wiring = _wiring_for_contract_runtime(runtime)

    result = wiring.run_phase_b(
        _phase_a(
            player_id,
            tool_call={
                "name": "contract_unknown_tool",
                "arguments": {"probe": "x"},
            },
        )
    )

    assert result.success is False
    assert result.error_code == "UNSUPPORTED_TOOL"
    assert len(runtime.action_results) == 1
    entry = runtime.action_results[0]
    # #552 PR-A: 失敗パスの action_summary も共有 sanitizer に集約され、orchestrator と
    # 同じ「...) を実行しました。」形式に統一された (outcome arg "probe" は保持)。
    assert entry["action_summary"] == 'contract_unknown_tool({"probe": "x"}) を実行しました。'
    assert entry["tool_name"] == "contract_unknown_tool"
    assert entry["success"] is False
    assert entry["error_code"] == "UNSUPPORTED_TOOL"


def test_phase_b_generic_failure_passes_subjective_fields_to_the_record(
    clean_runtime_env: None,
) -> None:
    """sanitizer が JSON から主観入力を落とすので、失敗 (unsupported) 経路でも
    intention / emotion_hint を構造化フィールドとして _record_action_result に渡す。"""
    player_id = PlayerId(1)
    runtime = _ContractRuntime()
    wiring = _wiring_for_contract_runtime(runtime)

    wiring.run_phase_b(
        _phase_a(
            player_id,
            tool_call={
                "name": "contract_unknown_tool",
                "arguments": {
                    "probe": "x",
                    "intention": "試しに呼ぶ",
                    "emotion_hint": "curiosity",
                },
            },
        )
    )

    entry = runtime.action_results[0]
    # JSON からは落ちるが構造化フィールドには残る
    assert "intention" not in entry["action_summary"]
    assert entry["intention"] == "試しに呼ぶ"
    assert entry["emotion_hint"] == "curiosity"


def test_direct_explore_records_natural_language_action_summary(
    clean_runtime_env: None,
) -> None:
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]

    runtime.do_explore(player_id)

    entries = runtime._action_result_store.get_recent(player_id, 10)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.tool_name == TOOL_NAME_SPOT_GRAPH_EXPLORE
    assert entry.success is True
    assert entry.intention is None
    assert entry.emotion_hint is None
    assert entry.argument_fingerprint is None
    assert entry.should_reschedule is False
    assert entry.omit_result_in_prompt is False
    assert entry.action_summary == "「入口広間」の周辺を探索した"
    assert not entry.action_summary.startswith(f"{TOOL_NAME_SPOT_GRAPH_EXPLORE}(")


def test_direct_travel_start_records_scene_boundary_and_tick(
    clean_runtime_env: None,
) -> None:
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]
    tick_before = runtime.current_tick()
    graph = runtime._spot_graph_repo.find_graph()
    current_spot_id = graph.get_entity_spot(EntityId.create(int(player_id.value)))
    destination = next(
        iter(graph.iter_outgoing_connections_from(current_spot_id))
    ).to_spot_id
    destination_key = runtime.id_mapper.get_str("spot", destination.value)
    from_name = runtime.get_player_spot_name(player_id)
    destination_name = graph.get_spot(destination).name

    runtime.do_move(player_id, destination_key)

    entries = runtime._action_result_store.get_recent(player_id, 10)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.tool_name == TOOL_NAME_SPOT_GRAPH_TRAVEL_TO
    assert entry.success is True
    assert entry.scene_boundary is True
    assert entry.occurred_tick == tick_before
    assert (
        entry.action_summary
        == f"「{from_name}」から「{destination_name}」へ向かって出発した"
    )
    assert "移動中" in entry.result_summary


def test_direct_explore_carries_subjective_fields_when_passed(
    clean_runtime_env: None,
) -> None:
    """U2: do_explore に subjective kwargs を渡すと記録 entry に乗る (do_* → recorder 配線)。"""
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]

    runtime.do_explore(
        player_id,
        intention="出口を探す",
        emotion_hint="curiosity",
    )

    entry = runtime._action_result_store.get_recent(player_id, 1)[0]
    assert entry.intention == "出口を探す"
    assert entry.emotion_hint == "curiosity"


def test_direct_travel_carries_subjective_fields_when_passed(
    clean_runtime_env: None,
) -> None:
    """U2: do_move に subjective kwargs を渡すと記録 entry に乗る (travel の do_* → recorder 配線)。"""
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]
    graph = runtime._spot_graph_repo.find_graph()
    current_spot_id = graph.get_entity_spot(EntityId.create(int(player_id.value)))
    destination = next(
        iter(graph.iter_outgoing_connections_from(current_spot_id))
    ).to_spot_id
    destination_key = runtime.id_mapper.get_str("spot", destination.value)

    runtime.do_move(
        player_id,
        destination_key,
        intention="次の部屋へ進む",
        emotion_hint="determination",
    )

    entry = runtime._action_result_store.get_recent(player_id, 1)[0]
    assert entry.tool_name == TOOL_NAME_SPOT_GRAPH_TRAVEL_TO
    assert entry.intention == "次の部屋へ進む"
    assert entry.emotion_hint == "determination"


def test_explore_handler_threads_subjective_args_into_record(
    clean_runtime_env: None,
) -> None:
    """U2: explore handler が arguments の subjective を do_* 経由で記録する。

    PR-θ2 (経路統合) 後: 旧 ``_handle_explore`` は削除、新経路は
    ``_tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE]`` (=
    SpotGraphToolExecutor._explore を wire adapter でラップしたもの) 経由。
    subjective 記録経路は同じ ``runtime.do_explore`` に委譲するので、record 内容
    のアサーションは変わらない。

    露出スキーマが OFF でも、handler は arguments dict から直接読むため、
    arguments に値が入れば記録に届く (= スキーマ露出 PR が入った瞬間に流れる配線)。
    """
    from ai_rpg_world.application.llm.tool_constants import (
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
    )
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient(None),
    )

    handler = wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE]
    result = handler(
        player_id,
        {
            "inner_thought": "周囲を見る",
            "intention": "出口を探す",
            "emotion_hint": "curiosity",
            "say_inline": "何かないか見てみよう",
        },
        ToolRuntimeContextDto.empty(),
    )

    assert result.success is True
    entry = runtime._action_result_store.get_recent(player_id, 1)[0]
    assert entry.intention == "出口を探す"
    assert entry.emotion_hint == "curiosity"
    assert entry.free_text_argument_names == ("say_inline",)


def test_explore_handler_records_none_subjective_when_args_absent(
    clean_runtime_env: None,
) -> None:
    """U2: 露出 OFF の現状 (arguments に subjective キー無し) では全 None で記録され挙動不変。

    PR-θ2 (経路統合) 後: handler は ``_tool_handlers`` から取得する。
    """
    from ai_rpg_world.application.llm.tool_constants import (
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
    )
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient(None),
    )

    handler = wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE]
    handler(
        player_id,
        {"inner_thought": "周囲を見る"},
        ToolRuntimeContextDto.empty(),
    )

    entry = runtime._action_result_store.get_recent(player_id, 1)[0]
    assert entry.intention is None
    assert entry.emotion_hint is None


def test_semantic_env_does_not_override_explicit_config_off(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """world_runtime semantic flags follow ResolvedLlmRuntimeConfig, not direct env reads."""
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    monkeypatch.setenv("SEMANTIC_PASSIVE_TOP_K", "5")
    monkeypatch.setenv("SEMANTIC_LLM_GIST_ENABLED", "1")

    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(
            episodic_enabled=True,
            semantic_passive_top_k=0,
            semantic_llm_gist_enabled=False,
        )
    )
    stack = runtime._episodic_stack

    assert stack is not None
    assert stack.semantic_passive_top_k == 0
    assert stack.semantic_passive_recall is None
    assert stack.semantic_memory_store is None
    assert stack.memory_link_store is None


def test_experiment_wiring_stub_exposes_current_world_runtime_snapshot_surface(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    runtime = _create_runtime(ResolvedLlmRuntimeConfig.for_tests(episodic_enabled=True))

    stub = _wiring_stub_from_world_runtime(runtime)

    assert stub.memo_store is runtime._todo_store
    assert stub.episodic_episode_store is runtime._episodic_stack.episode_store
    assert stub.semantic_memory_store is None
    assert stub.memory_link_store is None
    assert stub.being_attachment_resolver is runtime.aux_being_resolver
    assert stub.being_repository is runtime._aux_being_repository


def test_experiment_wiring_stub_exposes_semantic_stores_when_enabled(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """experiment snapshot surface includes semantic and link stores after #547."""
    from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(
            episodic_enabled=True, semantic_passive_top_k=3
        )
    )

    stub = _wiring_stub_from_world_runtime(runtime)

    assert stub.semantic_memory_store is runtime._episodic_stack.semantic_memory_store
    assert stub.memory_link_store is runtime._episodic_stack.memory_link_store
    assert stub.semantic_memory_store is not None
    assert stub.memory_link_store is not None


# ── R2a: escape run_phase_b の trace 発火カバレッジ ──
# full wiring (LlmAgentOrchestrator) 退役に備え、ACTION / ACTION_RESULT / MEMO_HINT の
# trace 発火と tick_provider 例外耐性を escape 経路で固定する (旧
# test_orchestrator_trace_integration.py 相当を escape へ移植)。


class _CapturingRecorder:
    """記録された trace event を全部保持する recorder (escape 経路用)。"""

    def __init__(self) -> None:
        self.events: list = []

    def record(self, kind, *, tick=None, player_id=None, **payload):
        from types import SimpleNamespace

        self.events.append(
            SimpleNamespace(
                kind=str(kind), tick=tick, player_id=player_id, payload=dict(payload)
            )
        )
        return None

    def close(self) -> None:
        pass


_CONTRACT_PROBE_TOOL = "contract_probe"


def _run_probe_phase_b(runtime: _ContractRuntime, *, success: bool = True):
    """contract_probe を 1 つ登録して run_phase_b を 1 回回すヘルパ。"""
    wiring = _wiring_for_contract_runtime(runtime)

    def _handler(player_id, arguments, runtime_context):
        return LlmCommandResultDto(
            success=success,
            message="DTO_RESULT: 完了" if success else "DTO_RESULT: 失敗",
            error_code=None if success else "CONTRACT_FAILED",
        )

    wiring._tool_handlers[_CONTRACT_PROBE_TOOL] = _handler
    wiring.run_phase_b(
        _phase_a(
            PlayerId(1),
            tool_call={
                "name": _CONTRACT_PROBE_TOOL,
                "arguments": {"inner_thought": "見る", "expected_result": "X"},
            },
        )
    )
    return wiring


def test_phase_b_records_action_and_action_result_trace(
    clean_runtime_env: None,
) -> None:
    """成功 tool 実行で escape run_phase_b が ACTION + ACTION_RESULT を同 tick で trace 記録する。"""
    from ai_rpg_world.application.trace import TraceEventKind

    rec = _CapturingRecorder()
    runtime = _ContractRuntime()
    runtime.trace_recorder = rec

    _run_probe_phase_b(runtime)

    kinds = [e.kind for e in rec.events]
    assert TraceEventKind.ACTION in kinds
    assert TraceEventKind.ACTION_RESULT in kinds
    action = next(e for e in rec.events if e.kind == TraceEventKind.ACTION)
    result = next(e for e in rec.events if e.kind == TraceEventKind.ACTION_RESULT)
    assert action.player_id == 1
    assert action.tick == runtime.current_tick()  # = 7
    assert action.payload["tool"] == _CONTRACT_PROBE_TOOL
    assert result.tick == action.tick
    assert result.payload["tool"] == _CONTRACT_PROBE_TOOL
    assert result.payload["success"] is True


def test_phase_b_records_action_result_trace_on_failure(
    clean_runtime_env: None,
) -> None:
    """失敗 tool でも ACTION_RESULT が success=False / error_code 付きで trace 記録される。"""
    from ai_rpg_world.application.trace import TraceEventKind

    rec = _CapturingRecorder()
    runtime = _ContractRuntime()
    runtime.trace_recorder = rec

    _run_probe_phase_b(runtime, success=False)

    result = next(e for e in rec.events if e.kind == TraceEventKind.ACTION_RESULT)
    assert result.payload["success"] is False
    assert result.payload["error_code"] == "CONTRACT_FAILED"


def test_phase_b_trace_is_noop_when_recorder_absent(
    clean_runtime_env: None,
) -> None:
    """trace_recorder 未注入 (None) でも run_phase_b はクラッシュしない。"""
    runtime = _ContractRuntime()
    runtime.trace_recorder = None
    # 例外なく完了すること
    _run_probe_phase_b(runtime)


def test_phase_b_trace_tick_none_when_current_tick_raises(
    clean_runtime_env: None,
) -> None:
    """current_tick が例外を投げても trace 記録は継続する (tick=None)。"""
    from ai_rpg_world.application.trace import TraceEventKind

    class _RaisingTickRuntime(_ContractRuntime):
        def current_tick(self) -> int:
            raise RuntimeError("tick boom")

    rec = _CapturingRecorder()
    runtime = _RaisingTickRuntime()
    runtime.trace_recorder = rec

    _run_probe_phase_b(runtime)

    action = next(e for e in rec.events if e.kind == TraceEventKind.ACTION)
    assert action.tick is None


def test_phase_b_records_memo_hint_trace(
    clean_runtime_env: None,
) -> None:
    """memo 完了 hint 発火時に MEMO_HINT trace が memo_id/memo_content/similarity/tool_name 付きで記録される。

    escape では hint の『メッセージ追記』は別テストで担保済みだが、MEMO_HINT trace
    event 自体の発火は未カバーだったため移植する。旧 orchestrator trace test が見ていた
    memo_content も固定し、re-home の完全性を保つ (#564 レビュー反映)。"""
    from types import SimpleNamespace

    from ai_rpg_world.application.trace import TraceEventKind

    rec = _CapturingRecorder()
    runtime = _ContractRuntime()
    runtime.trace_recorder = rec
    from ai_rpg_world.domain.being.value_object.being_id import BeingId

    runtime._acting_being_for = lambda player_id: SimpleNamespace(  # noqa: ARG005
        being_id=BeingId("contract-test-being")
    )
    wiring = _wiring_for_contract_runtime(runtime)

    class _StubHintService:
        def detect(self, being_id, action_summary, message, *, excluded_ids=()):
            # #1322: detect は検出結果を返す。hint の有無とは別に、問うた判断と
            # 縮退の理由を同じ戻り値で運ぶ。
            return SimpleNamespace(
                hint=SimpleNamespace(
                    memo=SimpleNamespace(id="m1", content="祭壇を調べる"),
                    similarity=0.951,
                    source="overlap",
                    to_hint_text=lambda: " [memo 完了?: 祭壇を調べる]",
                ),
                judgments=(),
                unavailable_reason=None,
            )

    wiring.memo_completion_hint_service = _StubHintService()

    def _handler(player_id, arguments, runtime_context):
        return LlmCommandResultDto(success=True, message="調べた")

    wiring._tool_handlers[_CONTRACT_PROBE_TOOL] = _handler
    wiring.run_phase_b(
        _phase_a(
            PlayerId(1),
            tool_call={"name": _CONTRACT_PROBE_TOOL, "arguments": {"inner_thought": "x"}},
        )
    )

    memo_events = [e for e in rec.events if e.kind == TraceEventKind.MEMO_HINT]
    assert len(memo_events) == 1
    payload = memo_events[0].payload
    assert payload["memo_id"] == "m1"
    assert payload["memo_content"] == "祭壇を調べる"
    assert payload["similarity"] == 0.951
    assert payload["hint_source"] == "overlap"
    assert payload["tool_name"] == _CONTRACT_PROBE_TOOL
