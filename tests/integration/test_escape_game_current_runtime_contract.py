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

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
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


def test_episodic_on_exposes_episode_recall_with_semantic_default_off(
    clean_runtime_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
    runtime = _create_runtime()

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
        ResolvedLlmRuntimeConfig.for_tests(semantic_passive_top_k=3)
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
    runtime = _create_runtime()

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
        ResolvedLlmRuntimeConfig.for_tests(semantic_passive_top_k=3)
    )

    stub = _wiring_stub_from_escape_runtime(runtime)

    assert stub.semantic_memory_store is runtime._episodic_stack.semantic_memory_store
    assert stub.memory_link_store is runtime._episodic_stack.memory_link_store
    assert stub.semantic_memory_store is not None
    assert stub.memory_link_store is not None
