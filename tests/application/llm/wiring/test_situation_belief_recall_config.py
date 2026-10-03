"""【関連する学び】を状況の欄から引くかを profile から選び、組めない組み合わせを起動前に落とす (#1414)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


def _config(**values: str) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.from_mapping(values=values)


class TestTheProfileChoosesSituationRecall:
    """有効化と手法が profile から入り、既定では切れていることを保証する。"""

    def test_situation_recall_is_off_by_default(self) -> None:
        """何も書かなければ無効で、手法は 2 字組の BM25 になる。"""
        config = _config()

        assert config.situation_belief_recall_enabled is False
        assert config.situation_belief_recall_narrower == "char_bigram_bm25"

    def test_the_profile_turns_it_on_and_it_reaches_the_run_start_record(self) -> None:
        """有効化と手法を書くと解決済み設定に載り、run_start に残る trace 表現にも載る。"""
        config = _config(
            SEMANTIC_PASSIVE_TOP_K="3",
            SITUATION_BELIEF_RECALL_ENABLED="1",
            SITUATION_BELIEF_RECALL_NARROWER="char_bigram_bm25",
        )

        trace = config.to_trace_dict()
        assert trace["situation_belief_recall_enabled"] is True
        assert trace["situation_belief_recall_narrower"] == "char_bigram_bm25"


class TestFieldsToKeep:
    """残す欄の数が profile から入り、範囲外を起動前に落とすことを保証する。"""

    def test_two_fields_are_kept_by_default_and_the_profile_can_change_it(self) -> None:
        """何も書かなければ 2 つ、書けばその数が解決済み設定と run_start の記録に載る。"""
        assert _config().situation_fields_to_keep == 2
        config = _config(SITUATION_FIELDS_TO_KEEP="3")
        assert config.situation_fields_to_keep == 3
        assert config.to_trace_dict()["situation_fields_to_keep"] == 3

    @pytest.mark.parametrize("value", ["0", "6"])
    def test_out_of_range_is_rejected(self, value: str) -> None:
        """1〜5 の外の数は ValueError になる。"""
        with pytest.raises(ValueError, match="SITUATION_FIELDS_TO_KEEP"):
            _config(SITUATION_FIELDS_TO_KEEP=value)


class TestUnusableSettingsFailBeforeTheRun:
    """組めない設定を run の前に ValueError で落とすことを保証する。"""

    def test_unknown_narrower_is_rejected(self) -> None:
        """知らない手法の名前は ValueError になる。"""
        with pytest.raises(ValueError, match="situation_belief_recall_narrower"):
            _config(SITUATION_BELIEF_RECALL_NARROWER="embedding")

    def test_enabling_without_passive_top_k_is_rejected(self) -> None:
        """件数 (SEMANTIC_PASSIVE_TOP_K) が 0 のまま有効にすると ValueError になる。何も引かずに有効に見えるのを防ぐ。"""
        with pytest.raises(ValueError, match="SEMANTIC_PASSIVE_TOP_K"):
            _config(SITUATION_BELIEF_RECALL_ENABLED="1")

    def test_unparsable_flag_is_rejected_with_its_name(self) -> None:
        """真偽値として読めない値は、キーの名前を添えて ValueError になる。"""
        with pytest.raises(ValueError, match="SITUATION_BELIEF_RECALL_ENABLED"):
            _config(SITUATION_BELIEF_RECALL_ENABLED="maybe")
