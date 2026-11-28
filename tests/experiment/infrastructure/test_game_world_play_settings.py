from __future__ import annotations

import pytest

from ai_rpg_world.experiment.infrastructure.game_world_play_settings import GameWorldPlaySettings


class TestGameWorldPlaySettings:
    """GameWorldPlaySettings.from_runtime_config が、profile の runtime_config から新しい世界の設定を読み、読まない鍵と使えない値を断ることを保証する。"""

    def test_keys_shared_with_the_old_profile_are_read(self) -> None:
        """古い profile と同じ名前の鍵 (BEING_EPISODE_INDEX_LIMIT=5、MEMO_TOOLS_ENABLED=0) と、待つ人を起こす巡りの数を読む。"""
        settings = GameWorldPlaySettings.from_runtime_config(
            {"BEING_EPISODE_INDEX_LIMIT": "5", "MEMO_TOOLS_ENABLED": "0", "PLAY_WAKE_WAITING_AFTER_ROUNDS": "4"}
        )

        assert (settings.episode_index_limit, settings.memo_tools_enabled, settings.wake_waiting_after_rounds) == (
            5,
            False,
            4,
        )

    def test_missing_keys_take_the_defaults(self) -> None:
        """何も書かなければ、スタブで回し、メモと目次を出し、待つ人は 3 巡りで起こす。"""
        settings = GameWorldPlaySettings.from_runtime_config({})

        assert settings == GameWorldPlaySettings()
        assert (settings.llm_client, settings.wake_waiting_after_rounds) == ("stub", 3)

    def test_key_not_read_by_the_game_world_is_refused(self) -> None:
        """新しい世界が読まない鍵 (LLM_IDLE_TIMEOUT_TICKS) を書くと ValueError で断る。"""
        with pytest.raises(ValueError, match="LLM_IDLE_TIMEOUT_TICKS"):
            GameWorldPlaySettings.from_runtime_config({"LLM_IDLE_TIMEOUT_TICKS": "6"})

    def test_llm_client_not_available_yet_is_refused(self) -> None:
        """LLM_CLIENT に、新しい世界でまだ使えない litellm を書くと ValueError で断る。"""
        with pytest.raises(ValueError, match="LLM_CLIENT"):
            GameWorldPlaySettings.from_runtime_config({"LLM_CLIENT": "litellm"})

    @pytest.mark.parametrize("key", ["PLAY_WAKE_WAITING_AFTER_ROUNDS", "BEING_EPISODE_INDEX_LIMIT"])
    def test_counts_below_one_are_refused(self, key: str) -> None:
        """巡りの数や件数に 0 を書くと ValueError で断る。"""
        with pytest.raises(ValueError):
            GameWorldPlaySettings.from_runtime_config({key: "0"})

    def test_boolean_that_is_not_one_or_zero_is_refused(self) -> None:
        """真偽の鍵に 1 / 0 / true / false 以外 (yes) を書くと ValueError で断る。"""
        with pytest.raises(ValueError):
            GameWorldPlaySettings.from_runtime_config({"MEMO_TOOLS_ENABLED": "yes"})
