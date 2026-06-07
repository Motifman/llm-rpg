"""``LLM_IDLE_TIMEOUT_TICKS`` env override の挙動 (#346 Step 3)。

per-agent idle timer (= 旧 heartbeat interval) を env で実験ごとに調整
できることを保証する。デフォルト 6、env 指定で上書き、不正値はデフォルトに
フォールバック。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _LLM_IDLE_TIMEOUT_TICKS_DEFAULT,
    _resolve_llm_idle_timeout_ticks,
)


class TestResolveLlmIdleTimeoutTicks:
    """env 解決の境界条件。"""

    def test_env_未設定はデフォルト_6(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env 無し → 6 tick (#346 Step 3 既定)。"""
        monkeypatch.delenv("LLM_IDLE_TIMEOUT_TICKS", raising=False)
        assert _resolve_llm_idle_timeout_ticks() == _LLM_IDLE_TIMEOUT_TICKS_DEFAULT
        assert _LLM_IDLE_TIMEOUT_TICKS_DEFAULT == 6

    def test_env_で_24_に上げられる(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """1 日 (24 tick) 沈黙許容を試したい場合の長め設定。"""
        monkeypatch.setenv("LLM_IDLE_TIMEOUT_TICKS", "24")
        assert _resolve_llm_idle_timeout_ticks() == 24

    def test_env_で_1_まで下げられる(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """旧 heartbeat 並の頻発を再現したい場合の最小値。"""
        monkeypatch.setenv("LLM_IDLE_TIMEOUT_TICKS", "1")
        assert _resolve_llm_idle_timeout_ticks() == 1

    def test_不正値はデフォルトに戻る(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """parse 失敗 → 既定値 (silent failure 回避)。"""
        monkeypatch.setenv("LLM_IDLE_TIMEOUT_TICKS", "abc")
        assert _resolve_llm_idle_timeout_ticks() == _LLM_IDLE_TIMEOUT_TICKS_DEFAULT

    def test_0_以下は_1_にクランプ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """heartbeat emitter 側は interval_ticks < 1 で ValueError なので、env 経由で
        0 / 負値が渡らないように事前クランプする。"""
        monkeypatch.setenv("LLM_IDLE_TIMEOUT_TICKS", "0")
        assert _resolve_llm_idle_timeout_ticks() == 1
        monkeypatch.setenv("LLM_IDLE_TIMEOUT_TICKS", "-5")
        assert _resolve_llm_idle_timeout_ticks() == 1
