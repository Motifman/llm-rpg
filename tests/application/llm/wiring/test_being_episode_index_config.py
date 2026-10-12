"""エピソードの目次の並べ方・件数 N・呼び出しの上限 M を profile から選び、組めない組み合わせを起動前に落とす (#1623)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)

_WRITING = {"BEING_EPISODE_WRITING_ENABLED": "1", "SHORT_TERM_MEMORY_KIND": "rolling_summary"}


def _config(**values: str) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.from_mapping(values=values)


class TestTheProfileChoosesTheEpisodeIndex:
    """目次の設定が profile から入り、既定では目次を出さないことを保証する。"""

    def test_the_index_is_off_by_default(self) -> None:
        """何も書かなければ目次は出さず、N は 10、M は 3 になる。"""
        config = _config()

        assert (
            config.being_episode_index_order,
            config.being_episode_index_limit,
            config.being_episode_recall_max_handles,
        ) == ("off", 10, 3)

    @pytest.mark.parametrize("order", ["recalled_rises_to_top", "newest_first"])
    def test_the_profile_chooses_the_order_n_and_m(self, order: str) -> None:
        """並べ方・N・M を書くと、解決済み設定と run_start に残る trace 表現に載る。"""
        config = _config(
            BEING_EPISODE_INDEX_ORDER=order,
            BEING_EPISODE_INDEX_LIMIT="5",
            BEING_EPISODE_RECALL_MAX_HANDLES="2",
            **_WRITING,
        )

        traced = config.to_trace_dict()
        assert (
            traced["being_episode_index_order"],
            traced["being_episode_index_limit"],
            traced["being_episode_recall_max_handles"],
        ) == (order, 5, 2)

    def test_an_unknown_order_is_rejected(self) -> None:
        """並べ方に知らない名前を書くと、鍵の名前つきで ValueError にする。"""
        with pytest.raises(ValueError, match="BEING_EPISODE_INDEX_ORDER"):
            _config(BEING_EPISODE_INDEX_ORDER="by_importance", **_WRITING)

    @pytest.mark.parametrize("key", ["BEING_EPISODE_INDEX_LIMIT", "BEING_EPISODE_RECALL_MAX_HANDLES"])
    def test_zero_is_rejected(self, key: str) -> None:
        """N と M は 1 以上に限り、0 を書くと鍵の名前つきで ValueError にする。"""
        with pytest.raises(ValueError, match=key):
            _config(BEING_EPISODE_INDEX_ORDER="newest_first", **{key: "0"}, **_WRITING)

    def test_the_index_requires_episode_writing(self) -> None:
        """書き起こしを有効にしないまま目次を出そうとすると、起動前に ValueError で止める。"""
        with pytest.raises(ValueError, match="BEING_EPISODE_WRITING_ENABLED"):
            _config(BEING_EPISODE_INDEX_ORDER="newest_first")
