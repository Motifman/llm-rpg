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

- ``SHORT_TERM_MEMORY_KIND=rolling_summary`` を env で指定したら、実体も
  ``RollingSummaryShortTermMemory`` であること (PR #439 silent failure 再発防止)
- 上記 + ``LLM_CLIENT=litellm`` を組み合わせると、sliding_window 内部の
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
        "SHORT_TERM_MEMORY_KIND",
        "SHORT_TERM_MEMORY_SCHEDULER_MODE",
        "PROMPT_SECTION_ORDER",
        "LLM_CLIENT",
        "LLM_MODEL",
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "LLM_EPISODIC_ENABLED",
        "EPISODIC_EXPLORE_RELATED_ENABLED",
        "SEMANTIC_LLM_GIST_ENABLED",
        "SEMANTIC_PASSIVE_TOP_K",
        "SEMANTIC_SEARCH_ENABLED",
        "OPENAI_API_BASE",
        "OPENAI_API_KEY",
        "OPENROUTER_PROVIDER",
        "OPENROUTER_QUANTIZATION",
        "OPENROUTER_REQUIRE_PARAMS",
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
    """short_term_memory_kind 設定と実体の type が一致するか。

    PR #439 で silent failure (env=rolling_summary でも DefaultSlidingWindowMemory
    が使われていた) が発覚し fix された。本 test 群は再発防止。
    """

    def test_設定未指定なら_DefaultSlidingWindowMemory(self) -> None:
        """設定未指定 → default の DefaultSlidingWindowMemory が使われる。"""
        from ai_rpg_world.application.llm.services.sliding_window_memory import (
            DefaultSlidingWindowMemory,
        )

        runtime = _build_runtime()
        assert isinstance(runtime._sliding_window, DefaultSlidingWindowMemory)

    def test_sliding_window_明示_でも_DefaultSlidingWindowMemory(self) -> None:
        from ai_rpg_world.application.llm.services.sliding_window_memory import (
            DefaultSlidingWindowMemory,
        )

        runtime = _build_runtime(
            ResolvedLlmRuntimeConfig.for_tests(
                short_term_memory_kind="sliding_window"
            )
        )
        assert isinstance(runtime._sliding_window, DefaultSlidingWindowMemory)

    def test_rolling_summary_で_RollingSummaryShortTermMemory(self) -> None:
        """PR #439 silent failure 再発防止の核心 assert。"""
        from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
            RollingSummaryShortTermMemory,
        )

        runtime = _build_runtime(
            ResolvedLlmRuntimeConfig.for_tests(
                short_term_memory_kind="rolling_summary"
            )
        )
        assert isinstance(runtime._sliding_window, RollingSummaryShortTermMemory)


# ──────────────────────────────────────────────────────────────────
# Short-term memory: LLM 経路の実注入
# ──────────────────────────────────────────────────────────────────


class TestShortTermMemoryLlmServicesWired:
    """rolling_summary + LLM_CLIENT=litellm のとき、summary_service が実体注入される。

    PR #444 で silent failure (setter は存在するが呼び出し側 wiring が未実装で
    L4 / L5 が全件 template fallback だった) が fix された。本 test 群は再発防止。
    """

    def test_rolling_summary_と_stub_client_の組み合わせは_summary_service_None(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_CLIENT=stub なら LiteLLMClient ではないので summary_service は注入されない
        (= template fallback mode で動く / これは正しい挙動)。"""
        from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
            RollingSummaryShortTermMemory,
        )

        runtime = _build_runtime(
            ResolvedLlmRuntimeConfig.for_tests(
                short_term_memory_kind="rolling_summary",
                llm_client_kind="stub",
            )
        )
        sw = runtime._sliding_window
        assert isinstance(sw, RollingSummaryShortTermMemory)
        # stub なので LLM 経路は注入されない
        assert sw._service is None
        assert sw._long_service is None

    def test_rolling_summary_と_litellm_client_の組み合わせは_summary_service_注入(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PR #444 fix の核心 assert: rolling + litellm なら setter 注入が走り、
        ``_service`` / ``_long_service`` が None でなくなる。

        PR #444 前は呼び出し側 wiring が未実装で、ここが None のまま動いていた
        (= L4 / L5 が全件 template fallback)。
        """
        from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
            RollingSummaryShortTermMemory,
        )
        from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
            ShortTermMemorySummaryService,
        )
        from ai_rpg_world.application.llm.services.short_term_memory_long_summary_service import (
            ShortTermMemoryLongSummaryService,
        )

        runtime = _build_runtime(
            ResolvedLlmRuntimeConfig.for_tests(
                short_term_memory_kind="rolling_summary",
                llm_client_kind="litellm",
                llm_model="openai/gpt-4o-mini",
                llm_api_key="sk-test-dummy",
            )
        )
        sw = runtime._sliding_window
        assert isinstance(sw, RollingSummaryShortTermMemory)
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

    def test_litellm_で_timeout_が_有限値(self) -> None:
        from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient
        from ai_rpg_world.application.llm.wiring._llm_client_factory import (
            create_llm_client_from_config,
        )

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

    def test_config_timeout_が_反映される(self) -> None:
        from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient
        from ai_rpg_world.application.llm.wiring._llm_client_factory import (
            create_llm_client_from_config,
        )

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
# Section order: env <-> 実体一致
# ──────────────────────────────────────────────────────────────────


class TestSectionOrderConfigVsRuntime:
    """prompt_section_order 設定と prompt builder の strategy が一致する。"""

    def test_設定未指定なら_stable_to_volatile_default(self) -> None:
        from ai_rpg_world.application.llm.services.context_format_strategy import (
            SECTION_ORDER_STABLE_TO_VOLATILE,
        )

        runtime = _build_runtime()
        # context_strategy field が存在する想定。なければ test を更新
        strategy = getattr(runtime, "_context_strategy", None)
        assert strategy is not None
        assert strategy.section_order == SECTION_ORDER_STABLE_TO_VOLATILE

    def test_legacy_明示で_legacy_strategy(self) -> None:
        from ai_rpg_world.application.llm.services.context_format_strategy import (
            SECTION_ORDER_LEGACY,
        )

        runtime = _build_runtime(
            ResolvedLlmRuntimeConfig.for_tests(prompt_section_order="legacy")
        )
        strategy = getattr(runtime, "_context_strategy", None)
        assert strategy is not None
        assert strategy.section_order == SECTION_ORDER_LEGACY


# ──────────────────────────────────────────────────────────────────
# run_start trace payload <-> 実体一致 (= config-init split 検出)
# ──────────────────────────────────────────────────────────────────


class TestConfigInjection:
    """PR #448 (PR 3/6): create_world_runtime に ResolvedLlmRuntimeConfig
    を直接渡せる経路の確認。entrypoint が一度だけ ``from_mapping()`` を呼んで全部に
    渡し回す形を構造で保証する。"""

    def test_明示_cfg_を_渡すと_cfg_を_使う(self) -> None:
        """cfg を渡したら、その値で配線される。

        = 設定入力経路を 1 つにする原則の構造的保証。
        """
        from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
            RollingSummaryShortTermMemory,
        )
        from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
            ResolvedLlmRuntimeConfig,
        )
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        cfg = ResolvedLlmRuntimeConfig.for_tests(
            short_term_memory_kind="rolling_summary",
        )
        runtime = create_world_runtime(_SCENARIO, config=cfg)
        assert isinstance(runtime._sliding_window, RollingSummaryShortTermMemory)

    def test_cfg_省略時は空設定_default(self) -> None:
        """cfg 引数省略時は環境変数を読まず、空設定の既定値になる。"""
        from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
            RollingSummaryShortTermMemory,
        )
        from ai_rpg_world.application.llm.services.sliding_window_memory import (
            DefaultSlidingWindowMemory,
        )
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        runtime = create_world_runtime(_SCENARIO)  # cfg 省略
        assert not isinstance(runtime._sliding_window, RollingSummaryShortTermMemory)
        assert isinstance(runtime._sliding_window, DefaultSlidingWindowMemory)


class TestRunStartTraceVsRuntime:
    """run_scenario_experiment.py が run_start trace に書く設定と、実体の
    runtime 内部の type が一致するか。

    PR #439 silent failure はまさにこのズレ (trace は rolling_summary と書くが
    実体は DefaultSlidingWindowMemory) だった。本 test で「trace に出る値」と
    「runtime の実体」が同じ config から派生していることを構造的に保証する。
    """

    def test_rolling_summary_config_が_RollingSummary_実装と_一致(self) -> None:
        """trace に出す config と runtime の sliding_window type が同一 cfg から決まる。"""
        from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
            RollingSummaryShortTermMemory,
        )

        cfg = ResolvedLlmRuntimeConfig.for_tests(
            short_term_memory_kind="rolling_summary"
        )
        assert cfg.to_trace_dict()["short_term_memory_kind"] == "rolling_summary"

        runtime = _build_runtime(cfg)
        assert isinstance(runtime._sliding_window, RollingSummaryShortTermMemory), (
            "config で rolling_summary を指定したのに、実体は "
            f"{type(runtime._sliding_window).__name__}。"
            "PR #439 silent failure (config-init split) が再発している"
        )
