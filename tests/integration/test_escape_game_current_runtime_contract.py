"""Current escape_game runtime behavior contracts.

These are characterization tests for the runtime path used by
``make experiment`` and the spot_graph_game server. They intentionally capture
today's behavior before further runtime convergence work.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    ToolDefinitionDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _EscapeGameLlmWiring,
    _LlmPhaseAResult,
)


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


@pytest.fixture()
def clean_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep these contract tests independent from the caller's shell env."""
    for key in (
        "LLM_EPISODIC_ENABLED",
        "LLM_EPISODIC_SUBJECTIVE_ENABLED",
        "SEMANTIC_PASSIVE_TOP_K",
        "SEMANTIC_LLM_GIST_ENABLED",
        "SEMANTIC_SEARCH_ENABLED",
        "SHORT_TERM_MEMORY_KIND",
        "PROMPT_SECTION_ORDER",
        "LLM_TOOL_MODE",
    ):
        monkeypatch.delenv(key, raising=False)


def _create_runtime(config: ResolvedLlmRuntimeConfig | None = None):
    from ai_rpg_world.application.escape_game.escape_game_runtime import (
        create_escape_game_runtime,
    )

    return create_escape_game_runtime(
        _SCENARIO_PATH,
        config=config or ResolvedLlmRuntimeConfig.for_tests(),
    )


def _user_prompt_text(prompt: dict) -> str:
    return "\n".join(
        m.get("content", "")
        for m in prompt.get("messages", [])
        if m.get("role") == "user"
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
        self.calls: list[int] = []

    def on_after_tool_turn(self, player_id: int) -> None:
        self.calls.append(player_id)


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

    def after_action_recorded(self, player_id: PlayerId) -> None:
        self.events.append("chunk")
        self.calls.append(player_id)


class _OrderedPromotionSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[int] = []

    def on_after_tool_turn(self, player_id: int) -> None:
        self.events.append("promotion")
        self.calls.append(player_id)


class _RaisingChunkCoordinatorSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def after_action_recorded(self, player_id: PlayerId) -> None:
        self.events.append("chunk")
        raise RuntimeError("chunk failed")


class _RaisingPromotionSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def on_after_tool_turn(self, player_id: int) -> None:
        self.events.append("promotion")
        raise RuntimeError("promotion failed")


class _LoopGuardSpy:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[tuple[PlayerId, str, dict]] = []

    def record_and_check(
        self,
        player_id: PlayerId,
        tool_name: str,
        arguments: dict,
    ) -> None:
        self.events.append("loop_guard")
        self.calls.append((player_id, tool_name, arguments))


class _ContractRuntime:
    def __init__(self, events: list[str] | None = None) -> None:
        self._obs_buffer = DefaultObservationContextBuffer()
        self.events = events if events is not None else []
        self.action_results: list[dict] = []
        self.trace_recorder = None

    def build_full_prompt(self, player_id: PlayerId) -> dict:
        return {
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
            "tool_runtime_context": ToolRuntimeContextDto.empty(),
        }

    def get_tool_definitions(self) -> list[ToolDefinitionDto]:
        return [
            ToolDefinitionDto(
                name=TOOL_NAME_SPOT_GRAPH_EXPLORE,
                description="explore",
                parameters={"type": "object", "properties": {}, "required": []},
            )
        ]

    def current_tick(self) -> int:
        return 7

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
        expected_result: str | None = None,
        intention: str | None = None,
        emotion_hint: str | None = None,
    ) -> None:
        # 実 escape _record_action_result (U2) と同じ subjective kwargs を受ける。
        self.events.extend(["append", "chunk", "promotion"])
        self.action_results.append(
            {
                "player_id": player_id,
                "action_summary": action_summary,
                "result_summary": result_summary,
                "tool_name": tool_name,
                "success": success,
                "error_code": error_code,
                "scene_boundary": scene_boundary,
                "expected_result": expected_result,
                "intention": intention,
                "emotion_hint": emotion_hint,
            }
        )


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


def _wiring_for_contract_runtime(runtime: _ContractRuntime) -> _EscapeGameLlmWiring:
    return _EscapeGameLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        llm_client=StubLlmClient(None),
    )


def test_default_escape_game_prompt_is_spot_graph_and_semantic_free(
    clean_runtime_env: None,
) -> None:
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]

    prompt = runtime.build_full_prompt(player_id)
    user = _user_prompt_text(prompt)
    tool_names = [definition.name for definition in runtime.get_tool_definitions()]

    assert "【現在地と周囲】" in user
    assert "【直近の出来事】" in user
    assert "【関連する学び】" not in user
    assert "visible_tile_map" not in user
    assert "current_terrain_type" not in user
    assert "spot_graph_travel_to" in tool_names
    assert "memory_recall_episodes" not in tool_names
    assert runtime._episodic_stack is None


def _tool_by_name(runtime, name: str):
    for definition in runtime.get_tool_definitions():
        if definition.name == name:
            return definition
    raise AssertionError(f"tool {name} not found")


def test_reinterpretation_off_leaves_episodic_stack_without_coordinator(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U3: episodic ON / reinterpretation OFF では coordinator は組まれない (従来挙動)。"""
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    runtime = _create_runtime(ResolvedLlmRuntimeConfig.for_tests(episodic_enabled=True))
    assert runtime._episodic_stack is not None
    assert runtime._episodic_stack.reinterpretation_coordinator is None
    assert runtime._episodic_stack.recall_buffer_store is None


def test_reinterpretation_on_builds_coordinator_without_completion_under_stub(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U3: reinterpretation ON で coordinator が組まれる。stub client なので completion は
    None になり、prompt 用 recall_buffer_store は None のまま (graceful)。"""
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(
            episodic_enabled=True, episodic_reinterpretation_enabled=True
        )
    )
    stack = runtime._episodic_stack
    assert stack is not None
    assert stack.reinterpretation_coordinator is not None
    assert stack.reinterpretation_journal is not None
    # stub client = completion 無し → prompt は recall buffer を覗かない
    assert stack.recall_buffer_store is None


def test_expected_result_policy_off_exposes_no_prediction_field(
    clean_runtime_env: None,
) -> None:
    """U2 後続 v0: policy off (既定) では expected_result が schema にも prompt にも出ない。"""
    runtime = _create_runtime()  # for_tests default = off
    explore = _tool_by_name(runtime, TOOL_NAME_SPOT_GRAPH_EXPLORE)
    assert "expected_result" not in explore.parameters["properties"]
    player_id = runtime.get_player_ids()[0]
    system = "\n".join(
        m.get("content", "")
        for m in runtime.build_full_prompt(player_id).get("messages", [])
        if m.get("role") == "system"
    )
    assert "expected_result" not in system


def test_expected_result_policy_optional_exposes_field_not_required(
    clean_runtime_env: None,
) -> None:
    """v0: optional で対象4ツールに expected_result が出るが required にならない。非対象には出ない。"""
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(expected_result_policy="optional")
    )
    for name in (
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
        TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        TOOL_NAME_SPOT_GRAPH_WAIT,
    ):
        defn = _tool_by_name(runtime, name)
        assert "expected_result" in defn.parameters["properties"], name
        assert "expected_result" not in defn.parameters.get("required", []), name
    # 非対象 tool (listen) には露出しない = 露出範囲 = 記録配線範囲
    listen = _tool_by_name(runtime, TOOL_NAME_SPOT_GRAPH_LISTEN)
    assert "expected_result" not in listen.parameters["properties"]
    # prompt にも予測ルール行が出る
    player_id = runtime.get_player_ids()[0]
    system = "\n".join(
        m.get("content", "")
        for m in runtime.build_full_prompt(player_id).get("messages", [])
        if m.get("role") == "system"
    )
    assert "expected_result" in system


def test_expected_result_policy_required_makes_field_required(
    clean_runtime_env: None,
) -> None:
    """v0: required で対象4ツールの required に expected_result が入る。"""
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(expected_result_policy="required")
    )
    for name in (
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
        TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        TOOL_NAME_SPOT_GRAPH_WAIT,
    ):
        defn = _tool_by_name(runtime, name)
        assert "expected_result" in defn.parameters["required"], name


def test_escape_game_build_full_prompt_uses_shared_default_prompt_builder(
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

    tool_names = [definition.name for definition in runtime.get_tool_definitions()]
    assert "memory_recall_episodes" in tool_names


def test_semantic_config_wires_escape_game_stack_and_prompt_learning(
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
    """escape_game's action path calls the semantic promotion hook after chunk write."""
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

    assert spy.calls == [player_id.value]


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
    } <= set(store.kwargs)
    assert store.kwargs["occurred_at"].tzinfo is timezone.utc
    assert store.kwargs["tool_name"] == "contract_probe"
    # escape は当面 subjective fields を渡さない (#553 baseline / U2 で配線)
    assert store.kwargs["expected_result"] is None
    assert store.kwargs["intention"] is None
    assert store.kwargs["emotion_hint"] is None
    assert chunk.calls == [player_id]
    assert promotion.calls == [player_id.value]


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
    ("phase_a", "expected_tool_name", "expected_error_code"),
    [
        (
            _phase_a(PlayerId(1), tool_call=None),
            "no_tool_call",
            "NO_TOOL_CALL",
        ),
        (
            _phase_a(PlayerId(1), tool_call=None, exception=RuntimeError("boom")),
            "llm_api_failed",
            "LLM_API_FAILED",
        ),
    ],
)
def test_phase_b_records_llm_level_failures_as_failed_action_results(
    clean_runtime_env: None,
    phase_a: _LlmPhaseAResult,
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
    assert entry["action_summary"] == "LLM API 呼び出し"
    assert entry["tool_name"] == expected_tool_name
    assert entry["success"] is False
    assert entry["error_code"] == expected_error_code


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


def test_phase_b_generic_failure_preserves_expected_result_for_prediction_line(
    clean_runtime_env: None,
) -> None:
    """#552 PR-A: sanitizer が JSON から予測を落とすので、失敗 (unsupported) 経路でも
    構造化 expected_result を _record_action_result に渡し、失敗行の [予測:] を守る。"""
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
                    "expected_result": "未知ツールでも何か起きる",
                    "intention": "試しに呼ぶ",
                    "emotion_hint": "curiosity",
                },
            },
        )
    )

    entry = runtime.action_results[0]
    # JSON からは落ちるが構造化フィールドには残る
    assert "expected_result" not in entry["action_summary"]
    assert entry["expected_result"] == "未知ツールでも何か起きる"
    assert entry["intention"] == "試しに呼ぶ"
    # その entry を recent-events 行にすると失敗行に [予測:] が出る
    from ai_rpg_world.application.llm.contracts.chunk_encoding import (
        format_action_result_line_for_recent_events,
    )
    from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry

    line = format_action_result_line_for_recent_events(
        ActionResultEntry(
            occurred_at=datetime.now(timezone.utc),
            action_summary=entry["action_summary"],
            result_summary=entry["result_summary"],
            success=False,
            error_code=entry["error_code"],
            expected_result=entry["expected_result"],
        )
    )
    assert "[予測: 未知ツールでも何か起きる]" in line
    assert "[失敗]" in line


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
    assert entry.expected_result is None
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
        expected_result="周囲に出口の手がかりがある",
        intention="出口を探す",
        emotion_hint="curiosity",
    )

    entry = runtime._action_result_store.get_recent(player_id, 1)[0]
    assert entry.expected_result == "周囲に出口の手がかりがある"
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
        expected_result="廊下に出られる",
        intention="次の部屋へ進む",
        emotion_hint="determination",
    )

    entry = runtime._action_result_store.get_recent(player_id, 1)[0]
    assert entry.tool_name == TOOL_NAME_SPOT_GRAPH_TRAVEL_TO
    assert entry.expected_result == "廊下に出られる"
    assert entry.intention == "次の部屋へ進む"
    assert entry.emotion_hint == "determination"


def test_explore_handler_threads_subjective_args_into_record(
    clean_runtime_env: None,
) -> None:
    """U2: runtime_manager._handle_explore が arguments の subjective を do_* 経由で記録する。

    露出スキーマが OFF でも、handler は arguments dict から直接読むため、
    arguments に値が入れば記録に届く (= スキーマ露出 PR が入った瞬間に流れる配線)。
    """
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]
    wiring = _EscapeGameLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        llm_client=StubLlmClient(None),
    )

    result = wiring._handle_explore(
        player_id,
        {
            "inner_thought": "周囲を見る",
            "expected_result": "出口の手がかりが見つかる",
            "intention": "出口を探す",
            "emotion_hint": "curiosity",
        },
        ToolRuntimeContextDto.empty(),
    )

    assert result.success is True
    entry = runtime._action_result_store.get_recent(player_id, 1)[0]
    assert entry.expected_result == "出口の手がかりが見つかる"
    assert entry.intention == "出口を探す"
    assert entry.emotion_hint == "curiosity"


def test_explore_handler_records_none_subjective_when_args_absent(
    clean_runtime_env: None,
) -> None:
    """U2: 露出 OFF の現状 (arguments に subjective キー無し) では全 None で記録され挙動不変。"""
    runtime = _create_runtime()
    player_id = runtime.get_player_ids()[0]
    wiring = _EscapeGameLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        llm_client=StubLlmClient(None),
    )

    wiring._handle_explore(
        player_id,
        {"inner_thought": "周囲を見る"},
        ToolRuntimeContextDto.empty(),
    )

    entry = runtime._action_result_store.get_recent(player_id, 1)[0]
    assert entry.expected_result is None
    assert entry.intention is None
    assert entry.emotion_hint is None


def test_semantic_env_does_not_override_explicit_config_off(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """escape_game semantic flags follow ResolvedLlmRuntimeConfig, not direct env reads."""
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


def test_experiment_wiring_stub_exposes_current_escape_game_snapshot_surface(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.run_scenario_experiment import _wiring_stub_from_escape_runtime

    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    runtime = _create_runtime(ResolvedLlmRuntimeConfig.for_tests(episodic_enabled=True))

    stub = _wiring_stub_from_escape_runtime(runtime)

    assert stub.memo_store is runtime._todo_store
    assert stub.episodic_episode_store is runtime._episodic_stack.episode_store
    assert stub.semantic_memory_store is None
    assert stub.memory_link_store is None
    assert stub.episodic_recall_buffer_store is None
    assert stub.episodic_reinterpretation_journal_store is None
    assert stub.being_attachment_resolver is runtime.aux_being_resolver
    assert stub.being_repository is runtime._aux_being_repository


def test_experiment_wiring_stub_exposes_semantic_stores_when_enabled(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """experiment snapshot surface includes semantic and link stores after #547."""
    from scripts.run_scenario_experiment import _wiring_stub_from_escape_runtime

    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    runtime = _create_runtime(
        ResolvedLlmRuntimeConfig.for_tests(
            episodic_enabled=True, semantic_passive_top_k=3
        )
    )

    stub = _wiring_stub_from_escape_runtime(runtime)

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


def _run_probe_phase_b(runtime: "_ContractRuntime", *, success: bool = True):
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
    wiring = _wiring_for_contract_runtime(runtime)

    class _StubHintService:
        def detect(self, player_id, action_summary, message):
            return SimpleNamespace(
                memo=SimpleNamespace(id="m1", content="祭壇を調べる"),
                similarity=0.951,
                to_hint_text=lambda: " [memo 完了?: 祭壇を調べる]",
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
    assert payload["tool_name"] == _CONTRACT_PROBE_TOOL
