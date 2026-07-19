"""``LLM_IDLE_TIMEOUT_TICKS`` を runtime_config で解決する挙動。

per-agent idle timer (= 旧 heartbeat interval) は実験条件なので、
環境変数ではなく ``ResolvedLlmRuntimeConfig`` の単一窓口で解決する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


class TestResolveLlmIdleTimeoutTicks:
    """idle timeout tick の境界条件を config 解決で保証する。"""

    def test_未設定はデフォルト_6(self) -> None:
        """未設定なら 6 tick (#346 Step 3 既定)。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.llm_idle_timeout_ticks == 6

    def test_config_で_24_に上げられる(self) -> None:
        """1 日 (24 tick) 沈黙許容を試したい場合の長め設定。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={"LLM_IDLE_TIMEOUT_TICKS": "24"}
        )
        assert cfg.llm_idle_timeout_ticks == 24

    def test_config_で_1_まで下げられる(self) -> None:
        """旧 heartbeat 並の頻発を再現したい場合の最小値。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={"LLM_IDLE_TIMEOUT_TICKS": "1"}
        )
        assert cfg.llm_idle_timeout_ticks == 1

    def test_非数値は_ValueError(self) -> None:
        """parse 失敗は既定値縮退ではなく profile ミスとして止める。"""
        with pytest.raises(ValueError, match="LLM_IDLE_TIMEOUT_TICKS"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_IDLE_TIMEOUT_TICKS": "abc"}
            )

    def test_0_以下は_ValueError(self) -> None:
        """0 / 負値は heartbeat emitter に渡す前に fail-fast する。"""
        with pytest.raises(ValueError, match="LLM_IDLE_TIMEOUT_TICKS"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_IDLE_TIMEOUT_TICKS": "0"}
            )
        with pytest.raises(ValueError, match="LLM_IDLE_TIMEOUT_TICKS"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_IDLE_TIMEOUT_TICKS": "-5"}
            )
