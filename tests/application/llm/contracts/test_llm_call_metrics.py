"""LlmCallMetrics の境界挙動 (実験 #356 用 metrics)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.llm_call_metrics import (
    LlmCallMetrics,
)


class TestComputeTps:
    """compute_tps が 0 除算 / 0 トークン を安全に扱う。"""

    def test_per(self) -> None:
        """通常ケースは完了トークン per 壁時計秒。"""
        # 50 tokens / 2000 ms = 25 tps
        assert LlmCallMetrics.compute_tps(50, 2000) == 25.0

    def test_wall_latency_zero_0(self) -> None:
        """wall latency 0 なら 0。"""
        assert LlmCallMetrics.compute_tps(100, 0) == 0.0

    def test_wall_latency_negative_value_zero(self) -> None:
        """wall latency 負値 なら 0。"""
        assert LlmCallMetrics.compute_tps(100, -100) == 0.0

    def test_completion_tokens_zero_0(self) -> None:
        """completion tokens 0 なら 0。"""
        assert LlmCallMetrics.compute_tps(0, 1000) == 0.0


class TestMetricsDataclass:
    """LlmCallMetrics の生成と immutability。"""

    def test_all_dataclass(self) -> None:
        """全フィールドを dataclass で保持できる。"""
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

    def test_failure_error_code(self) -> None:
        """失敗時は errorcode が入る。"""
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

    def test_cached_tokens_default_zero(self) -> None:
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

    def test_cached_tokens_can_be_set_explicitly(self) -> None:
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

    def test_cost_usd_default_zero(self) -> None:
        """cost_usd 未指定なら 0.0 (OpenAI 直結 / vLLM 等で provider が返さない場合)。"""
        m = LlmCallMetrics(
            model="test/model",
            wall_latency_ms=1000,
            prompt_tokens=500,
            completion_tokens=20,
            tps=20.0,
            success=True,
        )
        assert m.cost_usd == 0.0

    def test_cost_usd_can_be_set_explicitly(self) -> None:
        """OpenRouter 経由なら provider 宣告の USD コストを保持する。"""
        m = LlmCallMetrics(
            model="openrouter/google/gemma-4-31b-it",
            wall_latency_ms=610,
            prompt_tokens=49,
            completion_tokens=7,
            tps=11.5,
            success=True,
            cost_usd=0.0000089,
        )
        assert m.cost_usd == pytest.approx(0.0000089)

    def test_phase_defaults_to_one_step(self) -> None:
        """呼び出し区分未指定なら既存 1段階ターンを示す one_step として扱う。"""
        m = LlmCallMetrics(
            model="test/model",
            wall_latency_ms=1000,
            prompt_tokens=500,
            completion_tokens=20,
            tps=20.0,
            success=True,
        )
        assert m.phase == "one_step"

    def test_phase_can_be_set_explicitly(self) -> None:
        """2段階ターン用に assess_phase / action_phase を呼び出し単位で保持できる。"""
        m = LlmCallMetrics(
            model="test/model",
            wall_latency_ms=1000,
            prompt_tokens=500,
            completion_tokens=20,
            tps=20.0,
            success=True,
            phase="assess_phase",
        )
        assert m.phase == "assess_phase"
