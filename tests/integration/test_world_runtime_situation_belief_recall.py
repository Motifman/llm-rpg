"""SITUATION_BELIEF_RECALL_ENABLED で、world_runtime の【関連する学び】が状況の項目から引く形に切り替わる配線を保証する (#1414)。

LLM と Jev は呼ばない。信念の store を読むだけ。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

# 循環 import 回避の warm-up。
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.runtime_config_helpers import episodic_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "forbidden_library_demo.json"
)


def _build_runtime(**overrides: Any):  # type: ignore[no-untyped-def]
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    return create_world_runtime(_SCENARIO_PATH, config=episodic_config(**overrides))


def _rin(runtime) -> PlayerId:  # type: ignore[no-untyped-def]
    for spawn in runtime.scenario.player_spawns:
        if spawn.name == "リン":
            return PlayerId(spawn.player_id)
    raise AssertionError("リン not found")


def _seed(runtime, player_id: PlayerId, entry_id: str, text: str) -> None:  # type: ignore[no-untyped-def]
    being = runtime.aux_being_resolver.resolve_being_id(
        runtime.aux_being_default_world_id, player_id
    )
    runtime._episodic_stack.semantic_memory_store.add_by_being(
        being,
        SemanticMemoryEntry(
            entry_id=entry_id,
            player_id=int(player_id.value),
            being_id=being,
            text=text,
            evidence_episode_ids=("ep-1",),
            confidence=0.7,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            importance_score=10,
        ),
    )


def _learned_section(runtime, player_id: PlayerId) -> str:  # type: ignore[no-untyped-def]
    prompt = runtime.build_full_prompt(player_id)
    return "\n".join(
        m.get("content", "") for m in prompt.get("messages", []) if m.get("role") == "user"
    )


class TestSituationRecallIsWiredOnlyWhenEnabled:
    """有効にしたときだけ【関連する学び】の引き方が変わることを保証する。"""

    def test_off_keeps_the_passive_recall_that_shows_unmatched_important_beliefs(self) -> None:
        """無効なら従来の受動想起のままで、状況に一致しない重要な信念も新しさと重要度で載る。"""
        runtime = _build_runtime(semantic_passive_top_k=3)
        rin = _rin(runtime)
        _seed(runtime, rin, "b-unrelated", "UNRELATED_MARKER 泉の水は冷たい")

        assert "UNRELATED_MARKER" in _learned_section(runtime, rin)
        assert runtime._get_or_build_default_prompt_builder()._situation_recall is None

    def test_on_recalls_by_situation_and_leaves_out_unmatched_beliefs(self) -> None:
        """有効なら、目的の文に一致する信念が載り、状況に一致しない信念は重要でも載らない。"""
        runtime = _build_runtime(
            semantic_passive_top_k=3, situation_belief_recall_enabled=True
        )
        rin = _rin(runtime)
        goal = runtime._reflect_objective_provider(rin)
        assert goal
        _seed(runtime, rin, "b-goal", f"GOAL_MARKER {goal}には順番がある")
        _seed(runtime, rin, "b-unrelated", "UNRELATED_MARKER 泉の水は冷たい")

        user = _learned_section(runtime, rin)

        assert "GOAL_MARKER" in user
        assert "UNRELATED_MARKER" not in user

    @pytest.mark.parametrize(
        ("enabled", "expected", "absent"),
        [
            (False, "semantic_passive_recall", "situation_belief_recall"),
            (True, "situation_belief_recall", "semantic_passive_recall"),
        ],
    )
    def test_exactly_one_of_the_recall_traces_is_recorded(
        self, enabled: bool, expected: str, absent: str
    ) -> None:
        """無効なら受動想起の trace だけが、有効なら状況の項目の trace だけが、プロンプト 1 回につき 1 件残る。"""
        from tests.trace_helpers import RecordingTraceRecorder

        runtime = _build_runtime(
            semantic_passive_top_k=3, situation_belief_recall_enabled=enabled
        )
        recorder = RecordingTraceRecorder()
        runtime.set_trace_recorder(recorder)

        runtime.build_full_prompt(_rin(runtime))

        assert len(recorder.payloads(expected)) == 1
        assert recorder.payloads(absent) == []
        if enabled:
            assert recorder.payloads(expected)[0]["failed"] is None

    def test_on_without_episodic_stack_fails_before_building_the_prompt(self) -> None:
        """episodic を組まない設定で有効にすると、プロンプトを組む前に ValueError で止まる。"""
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
        from tests.runtime_config_helpers import runtime_config

        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=runtime_config(
                semantic_passive_top_k=3, situation_belief_recall_enabled=True
            ),
        )

        with pytest.raises(ValueError, match="episodic stack"):
            runtime._get_or_build_default_prompt_builder()


class TestTheEmbeddingNarrowerInTheRun:
    """埋め込みの手法 (#1454) を profile で選んだとき、組めなければ始める前に止まり、API が落ちたら縮退が trace に残ることを保証する。"""

    def test_qwen3_without_a_key_fails_before_building_the_prompt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OpenRouter のキーが環境に無ければ、プロンプトを組む前に、キーの名前を添えた ValueError で止まる。"""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        runtime = _build_runtime(
            semantic_passive_top_k=3,
            situation_belief_recall_enabled=True,
            situation_belief_recall_narrower="qwen3_embedding_8b_openrouter",
        )

        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            runtime._get_or_build_default_prompt_builder()

    def test_an_api_failure_falls_back_to_bigrams_and_is_traced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """API が失敗しても想起は 2 字組で続き、trace に選んだ手法・使った手法・縮退の理由が残る。"""
        from ai_rpg_world.application.llm.services.embedding_narrowing import (
            EmbeddingUnavailableError,
        )
        from ai_rpg_world.infrastructure.llm.openrouter_embedder import OpenRouterEmbedder
        from tests.trace_helpers import RecordingTraceRecorder

        def down(self, texts):  # type: ignore[no-untyped-def]
            raise EmbeddingUnavailableError("HTTP 503: overloaded")

        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        monkeypatch.setattr(OpenRouterEmbedder, "_embed", down)
        runtime = _build_runtime(
            semantic_passive_top_k=3,
            situation_belief_recall_enabled=True,
            situation_belief_recall_narrower="qwen3_embedding_8b_openrouter",
        )
        rin = _rin(runtime)
        _seed(runtime, rin, "sem-a", "リンは書庫の鍵を探している")
        recorder = RecordingTraceRecorder()
        runtime.set_trace_recorder(recorder)

        runtime.build_full_prompt(rin)

        [payload] = recorder.payloads("situation_belief_recall")
        assert payload["failed"] is None
        assert payload["requested_narrower"] == "qwen3_embedding_8b_openrouter"
        assert payload["narrower"] == "char_bigram_bm25"
        assert "HTTP 503" in payload["fallback_reason"]
