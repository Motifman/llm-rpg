from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.aux_llm_call import AuxLlmCall, AuxLlmComponent
from ai_rpg_world.being.infrastructure.llm_backstory_writer import LlmBackstoryWriter
from ai_rpg_world.being.infrastructure.llm_episode_writer import LlmEpisodeWriter
from ai_rpg_world.experiment.infrastructure.game_world_play_settings import GameWorldPlaySettings
from ai_rpg_world.experiment.infrastructure.game_world_run import aux_call_payload, game_world_writers
from ai_rpg_world.infrastructure.llm import litellm_client
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient


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

    def test_unknown_llm_client_is_refused(self) -> None:
        """LLM_CLIENT に stub と litellm 以外 (random) を書くと ValueError で断る。"""
        with pytest.raises(ValueError, match="LLM_CLIENT"):
            GameWorldPlaySettings.from_runtime_config({"LLM_CLIENT": "random"})

    @pytest.mark.parametrize("key", ["PLAY_WAKE_WAITING_AFTER_ROUNDS", "BEING_EPISODE_INDEX_LIMIT"])
    def test_counts_below_one_are_refused(self, key: str) -> None:
        """巡りの数や件数に 0 を書くと ValueError で断る。"""
        with pytest.raises(ValueError):
            GameWorldPlaySettings.from_runtime_config({key: "0"})

    def test_boolean_that_is_not_one_or_zero_is_refused(self) -> None:
        """真偽の鍵に 1 / 0 / true / false 以外 (yes) を書くと ValueError で断る。"""
        with pytest.raises(ValueError):
            GameWorldPlaySettings.from_runtime_config({"MEMO_TOOLS_ENABLED": "yes"})


def _without_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    # 手元の .env の値でテストの結果が変わらないよう、読み込ませない
    monkeypatch.setattr(litellm_client, "_load_dotenv_if_available", lambda: None)


class TestLlmSettings:
    """GameWorldPlaySettings と game_world_writers が、LLM_CLIENT=litellm のときに古い profile と同じ LLM の鍵で LiteLLM のクライアントを組むことを保証する。"""

    def test_litellm_builds_one_client_for_choosing_and_writing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LLM_CLIENT=litellm と LLM_MODEL を書くと、行動を選ぶのも書き起こすのも同じ LiteLLMClient になり、呼ぶ前には endpoint に触れない。"""
        _without_dotenv(monkeypatch)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
        settings = GameWorldPlaySettings.from_runtime_config(
            {
                "LLM_CLIENT": "litellm",
                "LLM_MODEL": "openrouter/deepseek/deepseek-v4.1-flash",
                "LLM_REASONING_EFFORT": "low",
            }
        )

        writers = game_world_writers(settings)

        assert isinstance(writers.action_choosing, LiteLLMClient)
        assert isinstance(writers.episode_writer, LlmEpisodeWriter)
        assert isinstance(writers.backstory_writer, LlmBackstoryWriter)

    def test_missing_api_key_is_refused_before_the_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OPENAI_API_KEY が無いまま LLM_CLIENT=litellm で組むと、run を始める前に ValueError で断る。"""
        _without_dotenv(monkeypatch)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        settings = GameWorldPlaySettings.from_runtime_config(
            {"LLM_CLIENT": "litellm", "LLM_MODEL": "openrouter/deepseek/deepseek-v4.1-flash"}
        )

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            game_world_writers(settings)

    def test_llm_keys_are_refused_with_the_stub(self) -> None:
        """スタブのまま LLM_MODEL を書くと、効かない設定として ValueError で断る。"""
        with pytest.raises(ValueError, match="LLM_MODEL"):
            GameWorldPlaySettings.from_runtime_config({"LLM_MODEL": "openrouter/deepseek/deepseek-v4.1-flash"})

    def test_tool_choice_is_not_read(self) -> None:
        """新しい世界は tool_choice を required だけで扱うので、LLM_TOOL_CHOICE を書くと断る。"""
        with pytest.raises(ValueError, match="LLM_TOOL_CHOICE"):
            GameWorldPlaySettings.from_runtime_config({"LLM_CLIENT": "litellm", "LLM_TOOL_CHOICE": "auto"})

    def test_parallel_workers_below_one_is_refused(self) -> None:
        """同時に呼ぶ数の上限 LLM_TURN_PARALLEL_WORKERS に 0 を書くと ValueError で断り、書かなければ上限なし (None)。"""
        with pytest.raises(ValueError, match="LLM_TURN_PARALLEL_WORKERS"):
            GameWorldPlaySettings.from_runtime_config({"LLM_TURN_PARALLEL_WORKERS": "0"})
        assert GameWorldPlaySettings.from_runtime_config({}).turn_parallel_workers is None

    def test_writing_calls_are_forwarded_to_where_the_run_writes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """litellm で組んだクライアントの補助の呼び出しの受け口は、遊びを始めるときに渡した書く先へ、呼び出しを 1 件ずつ回す。"""
        _without_dotenv(monkeypatch)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
        writers = game_world_writers(
            GameWorldPlaySettings.from_runtime_config(
                {"LLM_CLIENT": "litellm", "LLM_MODEL": "openrouter/deepseek/deepseek-v4.1-flash"}
            )
        )
        written: list[dict[str, object]] = []
        call = AuxLlmCall(component=AuxLlmComponent.EPISODE_WRITING, model="m", wall_latency_ms=900, success=True)

        assert writers.aux_calls is not None
        writers.aux_calls.forward_to(lambda forwarded: written.append(aux_call_payload(forwarded)))
        writers.aux_calls.record(call)

        [payload] = written
        assert (payload["component"], payload["wall_latency_ms"], payload["success"]) == ("episode_writing", 900, True)
