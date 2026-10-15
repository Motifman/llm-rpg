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

- 短期記憶の実体が ``SummarizingShortTermMemory`` であること (PR #439 silent failure 再発防止)
- 上記 + ``LLM_CLIENT=litellm`` を組み合わせると、短期記憶の
  ``_service`` (= 短期記憶要約 LLM 経路) が **None ではなく** 注入されていること
  (PR #444 silent failure 再発防止)
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
        "LLM_EPISODIC_ENABLED",
        "SEMANTIC_LLM_GIST_ENABLED",
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


class TestShortTermMemoryConfigVsRuntime:
    """設定から組んだ短期記憶の実体が、畳んで要約する短期記憶になるか。

    PR #439 で silent failure (env=rolling_summary でも DefaultSlidingWindowMemory
    が使われていた) が発覚し fix された。本 test 群は再発防止。
    """

    def test_config_unspecified_default_short_term_memory(self) -> None:
        """設定未指定 → default の SummarizingShortTermMemory が使われる (#1631)。"""
        from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
            SummarizingShortTermMemory,
        )

        runtime = _build_runtime()
        assert isinstance(runtime._short_term_memory, SummarizingShortTermMemory)

    def test_turn_window_settings_reach_the_memory(self) -> None:
        """profile の cap / 畳む数が短期記憶に配線される。"""
        runtime = _build_runtime(
            ResolvedLlmRuntimeConfig.for_tests(
                short_term_memory_turn_cap=12,
                short_term_memory_turn_compact_count=4,
            )
        )

        assert runtime._short_term_memory._turn_cap == 12
        assert runtime._short_term_memory._compact_turn_count == 4


# ──────────────────────────────────────────────────────────────────
# Short-term memory: LLM 経路の実注入
# ──────────────────────────────────────────────────────────────────


class TestShortTermMemoryLlmServicesWired:
    """rolling_summary + LLM_CLIENT=litellm のとき、summary_service が実体注入される。

    PR #444 で silent failure (setter は存在するが呼び出し側 wiring が未実装で
    L4 / L5 が全件 template fallback だった) が fix された。本 test 群は再発防止。
    """

    def test_rolling_summary_stub_client_summary_service_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_CLIENT=stub なら LiteLLMClient ではないので summary_service は注入されない
        (= template fallback mode で動く / これは正しい挙動)。"""
        from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
            SummarizingShortTermMemory,
        )

        runtime = _build_runtime(
            ResolvedLlmRuntimeConfig.for_tests(
                llm_client_kind="stub",
            )
        )
        sw = runtime._short_term_memory
        assert isinstance(sw, SummarizingShortTermMemory)
        # stub なので LLM 経路は注入されない
        assert sw._service is None
        assert sw._long_service is None

    def test_rolling_summary_litellm_client_summary_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PR #444 fix の核心 assert: rolling + litellm なら setter 注入が走り、
        ``_service`` / ``_long_service`` が None でなくなる。

        PR #444 前は呼び出し側 wiring が未実装で、ここが None のまま動いていた
        (= L4 / L5 が全件 template fallback)。
        """
        from ai_rpg_world.application.llm.services.short_term_memory_long_summary_service import (
            ShortTermMemoryLongSummaryService,
        )
        from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
            ShortTermMemorySummaryService,
        )
        from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
            SummarizingShortTermMemory,
        )

        runtime = _build_runtime(
            ResolvedLlmRuntimeConfig.for_tests(
                llm_client_kind="litellm",
                llm_model="openai/gpt-4o-mini",
                llm_api_key="sk-test-dummy",
            )
        )
        sw = runtime._short_term_memory
        assert isinstance(sw, SummarizingShortTermMemory)
        # PR #444: LLM 経路が確実に注入される
        assert sw._service is not None, (
            "PR #444 silent failure 再発: rolling_summary + LLM_CLIENT=litellm "
            "なのに sliding_window._service=None。L4 が template fallback で動く危険"
        )
        assert isinstance(sw._service, ShortTermMemorySummaryService)
        assert sw._long_service is not None, (
            "PR #444 silent failure 再発: long_service が未注入で L5 が template fallback"
        )
        assert isinstance(sw._long_service, ShortTermMemoryLongSummaryService)
        # persona_resolver も注入される (= L4 / L5 が player ごとの persona を読める)
        assert sw._persona_resolver is not None


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
        """cfg を渡したら、その値で配線される。

        = 設定入力経路を 1 つにする原則の構造的保証。
        """
        from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
            SummarizingShortTermMemory,
        )
        from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
            ResolvedLlmRuntimeConfig,
        )
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        cfg = ResolvedLlmRuntimeConfig.for_tests(
            short_term_memory_turn_cap=12,
            short_term_memory_turn_compact_count=4,
        )
        runtime = create_world_runtime(_SCENARIO, config=cfg)
        assert isinstance(runtime._short_term_memory, SummarizingShortTermMemory)
        assert runtime._short_term_memory._turn_cap == 12

    def test_cfg_empty_config_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """cfg 引数省略時は環境変数の SHORT_TERM_MEMORY_TURN_CAP=99 を読まず、空設定の既定の 20 ターンになる。"""
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        monkeypatch.setenv("SHORT_TERM_MEMORY_TURN_CAP", "99")
        runtime = create_world_runtime(_SCENARIO)  # cfg 省略
        assert runtime._short_term_memory._turn_cap == 20
