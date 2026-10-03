"""信念を作る前の判断を profile から選び、組めない組み合わせを起動前に落とす (#1453)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)

_ON = {
    "LLM_EPISODIC_ENABLED": "1",
    "BELIEF_CONSOLIDATION_ENABLED": "1",
    "TYPED_JUDGMENT_PROVIDER": "stub",
    "BELIEF_CREATE_GATE_ENABLED": "1",
}


def _config(**values: str) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.from_mapping(values=values)


class TestTheProfileChoosesTheGate:
    """有効化・絞り込みの手法・K・閾値が profile から入ることを保証する。"""

    def test_the_gate_is_off_unless_the_profile_asks_for_it(self) -> None:
        """何も書かなければ無効で、手法・K・閾値は既定値になる。"""
        config = _config()

        assert config.belief_create_gate_enabled is False
        assert config.belief_candidate_narrower == "char_bigram_bm25"
        assert config.belief_candidate_top_k >= 1
        assert 0.0 < config.belief_create_gate_min_confidence <= 1.0

    def test_the_profile_sets_the_method_k_and_threshold(self) -> None:
        """手法・K・閾値を書くと、解決済み設定に載る。"""
        config = _config(
            **_ON,
            BELIEF_CANDIDATE_NARROWER="char_bigram_bm25",
            BELIEF_CANDIDATE_TOP_K="7",
            BELIEF_CREATE_GATE_MIN_CONFIDENCE="0.75",
        )

        assert config.belief_create_gate_enabled is True
        assert config.belief_candidate_top_k == 7
        assert config.belief_create_gate_min_confidence == 0.75

    def test_the_values_reach_the_run_start_record(self) -> None:
        """有効化・手法・K・閾値は run_start に残る trace 表現に載る。"""
        trace = _config(**_ON).to_trace_dict()

        assert trace["belief_create_gate_enabled"] is True
        assert trace["belief_candidate_narrower"] == "char_bigram_bm25"
        assert "belief_candidate_top_k" in trace
        assert "belief_create_gate_min_confidence" in trace


class TestUnusableSettingsFailBeforeTheRun:
    """組めない設定を run の前に ValueError で落とすことを保証する。"""

    def test_an_unknown_narrower_is_rejected(self) -> None:
        """知らない手法の名前は ValueError。BM25 へ黙って縮退しない。"""
        with pytest.raises(ValueError):
            _config(**_ON, BELIEF_CANDIDATE_NARROWER="embeding")

    def test_top_k_below_one_is_rejected(self) -> None:
        """K が 1 未満なら ValueError。"""
        with pytest.raises(ValueError):
            _config(**_ON, BELIEF_CANDIDATE_TOP_K="0")

    def test_the_gate_without_typed_judgment_is_rejected(self) -> None:
        """判断の provider が off のまま有効にすると ValueError。問う先が無い。"""
        values = dict(_ON, TYPED_JUDGMENT_PROVIDER="off")

        with pytest.raises(ValueError):
            _config(**values)

    def test_the_gate_without_belief_consolidation_is_rejected(self) -> None:
        """信念を固める処理が無効のまま有効にすると ValueError。gate が呼ばれない。"""
        values = dict(_ON, BELIEF_CONSOLIDATION_ENABLED="0")

        with pytest.raises(ValueError):
            _config(**values)

    def test_the_gate_without_episodic_memory_is_rejected(self) -> None:
        """エピソード記憶が無効のまま有効にすると ValueError。信念を固める処理が組まれない。"""
        values = dict(_ON, LLM_EPISODIC_ENABLED="0")

        with pytest.raises(ValueError):
            _config(**values)
