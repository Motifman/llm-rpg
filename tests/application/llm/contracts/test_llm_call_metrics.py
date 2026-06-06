"""LlmCallMetrics の境界挙動 (実験 #356 用 metrics)。"""

from __future__ import annotations

from ai_rpg_world.application.llm.contracts.llm_call_metrics import (
    LlmCallMetrics,
)


class TestComputeTps:
    """compute_tps が 0 除算 / 0 トークン を安全に扱う。"""

    def test_通常ケース_は_完了トークン_per_壁時計秒(self) -> None:
        # 50 tokens / 2000 ms = 25 tps
        assert LlmCallMetrics.compute_tps(50, 2000) == 25.0

    def test_wall_latency_0_なら_0(self) -> None:
        assert LlmCallMetrics.compute_tps(100, 0) == 0.0

    def test_wall_latency_負値_なら_0(self) -> None:
        assert LlmCallMetrics.compute_tps(100, -100) == 0.0

    def test_completion_tokens_0_なら_0(self) -> None:
        assert LlmCallMetrics.compute_tps(0, 1000) == 0.0


class TestMetricsDataclass:
    """LlmCallMetrics の生成と immutability。"""

    def test_全フィールドを_dataclass_で_保持できる(self) -> None:
        m = LlmCallMetrics(
            model="test/model",
            wall_latency_ms=1500,
            prompt_tokens=200,
            completion_tokens=30,
            tps=20.0,
            success=True,
            error_code=None,
        )
        assert m.model == "test/model"
        assert m.wall_latency_ms == 1500
        assert m.tps == 20.0
        assert m.success is True

    def test_失敗時は_error_code_が_入る(self) -> None:
        m = LlmCallMetrics(
            model="test/model",
            wall_latency_ms=200,
            prompt_tokens=0,
            completion_tokens=0,
            tps=0.0,
            success=False,
            error_code="LLM_RATE_LIMIT",
        )
        assert m.success is False
        assert m.error_code == "LLM_RATE_LIMIT"

    def test_cached_tokens_の_デフォルトは_0(self) -> None:
        """cached_tokens 未指定なら 0 (provider が返さない場合の挙動)。"""
        m = LlmCallMetrics(
            model="test/model",
            wall_latency_ms=1000,
            prompt_tokens=500,
            completion_tokens=20,
            tps=20.0,
            success=True,
        )
        assert m.cached_tokens == 0

    def test_cached_tokens_を_明示_設定できる(self) -> None:
        """prefix cache 効率の指標として cached_tokens を保持する。"""
        m = LlmCallMetrics(
            model="test/model",
            wall_latency_ms=1000,
            prompt_tokens=500,
            completion_tokens=20,
            tps=20.0,
            success=True,
            cached_tokens=350,
        )
        assert m.cached_tokens == 350
