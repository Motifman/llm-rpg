"""目次つきのエピソードの書き起こしを profile から有効にし、組めない組み合わせを起動前に落とす (#1626)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


def _config(**values: str) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.from_mapping(values=values)


class TestTheProfileChoosesEpisodeWriting:
    """書き起こしの有効化が profile から入り、既定では切れていて、古いエピソードのスイッチとは別であることを保証する。"""

    def test_episode_writing_is_off_by_default(self) -> None:
        """何も書かなければ、書き起こしは無効になる。"""
        assert _config().being_episode_writing_enabled is False

    def test_the_profile_turns_it_on_and_it_reaches_the_run_start_record(self) -> None:
        """有効にすると解決済み設定に載り、run_start に残る trace 表現にも載る。"""
        config = _config(
            BEING_EPISODE_WRITING_ENABLED="1", SHORT_TERM_MEMORY_KIND="rolling_summary"
        )

        assert config.to_trace_dict()["being_episode_writing_enabled"] is True

    def test_it_does_not_turn_on_the_old_episodes(self) -> None:
        """有効にしても、古いエピソード (SubjectiveEpisode) の記憶は有効にならない。"""
        config = _config(
            BEING_EPISODE_WRITING_ENABLED="1", SHORT_TERM_MEMORY_KIND="rolling_summary"
        )

        assert config.episodic_enabled is False

    def test_it_requires_the_rolling_summary(self) -> None:
        """短期記憶が畳んで要約する種類でなければ、起動前に ValueError で止める。"""
        with pytest.raises(ValueError, match="BEING_EPISODE_WRITING_ENABLED"):
            _config(BEING_EPISODE_WRITING_ENABLED="1", SHORT_TERM_MEMORY_KIND="sliding_window")

    def test_unreadable_value_is_rejected(self) -> None:
        """真偽として読めない値は、鍵の名前つきで ValueError にする。"""
        with pytest.raises(ValueError, match="BEING_EPISODE_WRITING_ENABLED"):
            _config(BEING_EPISODE_WRITING_ENABLED="maybe")
