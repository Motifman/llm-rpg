"""Production wiring の構造 smoke test (PR #445)。

# 何のため

PR #443 の実機 run で連続発覚した silent failure 系 bug (PR #439 / #441 / #444)
は、全部「production wiring 経由で runtime を 1 度組んで属性を見れば即座に発覚
する」種類だった。しかし当時の test suite には:

- ``test_survival_island_episodic_smoke.py`` (episodic on/off の wire 確認)
- ``test_world_episodic_wiring.py``               (episodic stack 内部)

など個別 wiring の確認はあったが、**「env と実体が一致しているか」「LLM 経路の
依存 (timeout / summary_service) が正しく注入されているか」を統合的に assert
するもの**は無かった。

本 test 群はそのギャップを埋める「**配線契約テスト**」:

- ゲームの出来事が Being の短期記憶に写され、``LLM_CLIENT=litellm`` なら いきさつを書く LLM の経路が
  スタブではなく LiteLLMClient につながっていること (PR #439 / #444 silent failure 再発防止。
  今の短期記憶を消すまでは、その実体と要約の LLM の経路を見ていた)
- ``LiteLLMClient`` の ``_timeout_seconds`` が **必ず有限値** で、litellm
  default 6000 秒のハングが起きない構造になっていること (PR #444 再発防止)
- env と実体の **型** が trace に書かれた値と一致すること (config-init split
  防止 / 将来 PR #446 で `ResolvedLlmRuntimeConfig` に集約予定)

# 設計指針

- 実 LLM API は呼ばない (`LLM_CLIENT=stub` または litellm を mock)
- in-memory scenario (survival_island_v2 等の既存 scenario JSON を流用)
- 1 tick も回さない: **構築直後の属性 assert** だけ。E2E 動作確認は別 test
  (test_survival_island_episodic_smoke.py 等) が担当
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)

_SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"
# 4 player / spot_graph / inventory / monster を全部含むので production wiring の
# 縮図として最も妥当。test_survival_island_episodic_smoke.py と同じ選択。
_SCENARIO = _SCENARIOS_DIR / "survival_island_v2.json"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """開発者の .env / 既存環境変数が test 結果を汚染しないように切り離す。

    PR #434 経緯: env 解決層は fail-fast 化されているが、テスト並列実行時に
    既存環境変数が混入するとケースごとに非決定的な挙動になりうる。本 fixture
    で関連 env を全て delete し、各 test が明示的に setenv する形にする。
    """
    for key in (
        "LLM_CLIENT",
        "LLM_MODEL",
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "OPENAI_API_BASE",
        "OPENAI_API_KEY",
        "OPENROUTER_PROVIDER",
        "OPENROUTER_QUANTIZATION",
    ):
        monkeypatch.delenv(key, raising=False)
    # litellm の dotenv 自動読込を抑える (.env 内の OPENAI_API_KEY 等が混入する)
    monkeypatch.setattr(
        "ai_rpg_world.infrastructure.llm.litellm_client._load_dotenv_if_available",
        lambda: None,
    )


def _build_runtime(config: Any = None) -> Any:
    """解決済み設定を渡して production runtime を構築する。"""
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    return create_world_runtime(_SCENARIO, config=config)


# ──────────────────────────────────────────────────────────────────
# Short-term memory: env <-> 実体一致
# ──────────────────────────────────────────────────────────────────


class TestBeingShortTermMemoryWiring:
    """本番の配線で、ゲームの出来事が Being の短期記憶に入り、いきさつを書く LLM の経路が設定どおりにつながることを保証する (design_decisions D1824-24)。

    今の短期記憶 (``SummarizingShortTermMemory``) を消す前は、ここでその実体と要約の LLM の経路を見ていた
    (PR #439 / #444 の静かな失敗の再発防止)。同じ形の失敗を、Being の短期記憶の配線で見張る。
    """

    def test_game_events_are_copied_into_the_being_short_term_memory(self) -> None:
        """ストアに足した出来事を、写す処理 (PlayerShortTermMemoryCopy) が聞いている。"""
        runtime = _build_runtime()

        assert runtime._being_short_term_memory_copy is not None
        assert runtime._being_short_term_memory_copy.on_appended in runtime._recent_event_store._append_listeners

    def test_stub_client_writes_backstories_with_the_stub_completion(self) -> None:
        """LLM_CLIENT=stub なら、いきさつはスタブの完了で書く。"""
        from ai_rpg_world.application.llm.services.stub_backstory_completion import stub_backstory_completion

        runtime = _build_runtime(ResolvedLlmRuntimeConfig.for_tests(llm_client_kind="stub"))

        assert _backstory_completion(runtime) is stub_backstory_completion

    def test_litellm_client_writes_backstories_through_the_client(self) -> None:
        """LLM_CLIENT=litellm なら、いきさつは LiteLLMClient の complete_short_term_summary_json で書く。スタブに落ちていない。"""
        from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

        runtime = _build_runtime(
            ResolvedLlmRuntimeConfig.for_tests(
                llm_client_kind="litellm",
                llm_model="openai/gpt-4o-mini",
                llm_api_key="sk-test-dummy",
            )
        )

        completion = _backstory_completion(runtime)
        assert isinstance(getattr(completion, "__self__", None), LiteLLMClient)
        assert completion.__name__ == "complete_short_term_summary_json"


def _backstory_completion(runtime: Any) -> Any:
    from ai_rpg_world.being.application.handlers.write_backstory_handler import WriteBackstoryHandler

    dispatcher = runtime._being_short_term_memory_store._handoff.__self__
    handlers = [
        r.handler.handler
        for r in dispatcher._after_commit
        if isinstance(getattr(r.handler, "handler", None), WriteBackstoryHandler)
    ]
    assert handlers, "いきさつを書くハンドラが登録されていない"
    return handlers[0]._write._writer._complete_json


# ──────────────────────────────────────────────────────────────────
# LiteLLMClient: timeout
# ──────────────────────────────────────────────────────────────────


class TestLiteLLMClientTimeout:
    """litellm の default request_timeout=6000 (= 100 分) ハングを防ぐため、
    LiteLLMClient は必ず有限値の timeout を持つことを保証する (PR #444)。"""

    def test_litellm_timeout_value(self) -> None:
        """litellm で timeout が有限値。"""
        from ai_rpg_world.application.llm.wiring._llm_client_factory import (
            create_llm_client_from_config,
        )
        from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

        client = create_llm_client_from_config(
            ResolvedLlmRuntimeConfig.for_tests(
                llm_client_kind="litellm",
                llm_api_key="sk-test-dummy",
            )
        )
        assert isinstance(client, LiteLLMClient)
        # default 90 秒 / 100 分ハングは起きない
        assert 0 < client._timeout_seconds < 600.0, (
            "PR #444 silent failure 再発: LiteLLMClient の timeout が異常値 "
            f"({client._timeout_seconds}s)。litellm default 6000 秒は許容しない"
        )

    def test_config_timeout(self) -> None:
        """configtimeout が反映される。"""
        from ai_rpg_world.application.llm.wiring._llm_client_factory import (
            create_llm_client_from_config,
        )
        from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

        client = create_llm_client_from_config(
            ResolvedLlmRuntimeConfig.for_tests(
                llm_client_kind="litellm",
                llm_api_key="sk-test-dummy",
                llm_request_timeout_seconds=45.0,
            )
        )
        assert isinstance(client, LiteLLMClient)
        assert client._timeout_seconds == 45.0


# ──────────────────────────────────────────────────────────────────
# 設定の注入経路
# ──────────────────────────────────────────────────────────────────


class TestConfigInjection:
    """PR #448 (PR 3/6): create_world_runtime に ResolvedLlmRuntimeConfig
    を直接渡せる経路の確認。entrypoint が一度だけ ``from_mapping()`` を呼んで全部に
    渡し回す形を構造で保証する。"""

    def test_uses_cfg(self) -> None:
        """cfg を渡したら、runtime はその cfg の値を設定として持つ。

        = 設定入力経路を 1 つにする原則の構造的保証。
        """
        from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
            ResolvedLlmRuntimeConfig,
        )
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        cfg = ResolvedLlmRuntimeConfig.for_tests(being_episode_index_limit=7)
        runtime = create_world_runtime(_SCENARIO, config=cfg)
        assert runtime._runtime_config.being_episode_index_limit == 7

    def test_cfg_empty_config_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cfg 引数省略時は環境変数の LLM_MODEL を読まず、空設定の既定 (モデル無し) になる。"""
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        monkeypatch.setenv("LLM_MODEL", "openrouter/google/gemma-4-31b-it")
        runtime = create_world_runtime(_SCENARIO)  # cfg 省略
        assert runtime._runtime_config.llm_model is None
