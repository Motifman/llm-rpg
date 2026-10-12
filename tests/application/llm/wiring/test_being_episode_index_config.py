"""目次つきのエピソードはスイッチを持たず常に入り、件数 N と呼び出しの上限 M だけを profile から選ぶことを保証する (#1623、#1626、#1631)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


def _config(**values: str) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.from_mapping(values=values)


class TestTheEpisodeIndexIsAlwaysOn:
    """書き起こしと目次は設定で止められず、N と M だけが profile から入ることを保証する。"""

    def test_n_and_m_default_to_ten_and_three(self) -> None:
        """何も書かなければ、N は 10、M は 3 になる。"""
        config = _config()

        assert (
            config.being_episode_index_limit,
            config.being_episode_recall_max_handles,
        ) == (10, 3)

    def test_the_profile_chooses_n_and_m(self) -> None:
        """N と M を書くと、解決済み設定と run_start に残る trace 表現に載る。"""
        config = _config(BEING_EPISODE_INDEX_LIMIT="5", BEING_EPISODE_RECALL_MAX_HANDLES="2")

        traced = config.to_trace_dict()
        assert (
            traced["being_episode_index_limit"],
            traced["being_episode_recall_max_handles"],
        ) == (5, 2)

    @pytest.mark.parametrize("key", ["BEING_EPISODE_INDEX_LIMIT", "BEING_EPISODE_RECALL_MAX_HANDLES"])
    def test_zero_is_rejected(self, key: str) -> None:
        """N と M は 1 以上に限り、0 を書くと鍵の名前つきで ValueError にする。"""
        with pytest.raises(ValueError, match=key):
            _config(**{key: "0"})

    @pytest.mark.parametrize(
        "key", ["BEING_EPISODE_WRITING_ENABLED", "BEING_EPISODE_INDEX_ORDER"]
    )
    def test_the_removed_switches_are_rejected_as_unknown(self, key: str) -> None:
        """消したスイッチを書くと、黙って無視せず unknown runtime_config key の ValueError にする。"""
        with pytest.raises(ValueError, match=f"unknown runtime_config key.*{key}"):
            _config(**{key: "off"})

    def test_the_sliding_window_is_rejected(self) -> None:
        """短期記憶が畳まない sliding_window だと、書き起こしを呼べないので起動前に ValueError で止める。"""
        with pytest.raises(ValueError, match="SHORT_TERM_MEMORY_KIND must be rolling_summary"):
            _config(SHORT_TERM_MEMORY_KIND="sliding_window")

    def test_the_old_episodes_stay_off(self) -> None:
        """目次つきのエピソードが常に入っても、古いエピソード (SubjectiveEpisode) の記憶は有効にならない。"""
        assert _config().episodic_enabled is False
