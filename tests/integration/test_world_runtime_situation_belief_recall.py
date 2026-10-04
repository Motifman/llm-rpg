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
        from tests.application.being.expectation.support import RecordingTraceRecorder

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


class TestTheProfileNarrowerReachesTheRecall:
    """profile で選んだ絞り込みの手法が想起に使われ、trace に名前が残ることを保証する (#1498)。"""

    @pytest.mark.parametrize("narrower", ["char_bigram_bm25", "janome_bm25", "sudachi_bm25"])
    def test_the_recall_trace_names_the_chosen_narrower(self, narrower: str) -> None:
        """SITUATION_BELIEF_RECALL_NARROWER に書いた手法の名前が、situation_belief_recall の trace の narrower に残る。"""
        from tests.application.being.expectation.support import RecordingTraceRecorder

        runtime = _build_runtime(
            semantic_passive_top_k=3,
            situation_belief_recall_enabled=True,
            situation_belief_recall_narrower=narrower,
        )
        recorder = RecordingTraceRecorder()
        runtime.set_trace_recorder(recorder)

        runtime.build_full_prompt(_rin(runtime))

        assert [p["narrower"] for p in recorder.payloads("situation_belief_recall")] == [narrower]
