"""``wiring/feature_flags.py`` の env-driven knob 解決テスト。

Phase 1a 配線: ``EPISODIC_EXPLORE_RELATED_ENABLED`` を env-driven にした。
default OFF とすることで、エピソード記憶 (生成 / passive recall) の検証中に
能動探索 tool を expose せず、検証変数の交絡を避ける。

詳細: ``docs/memory_system/semantic_memory_activation_plan.md`` §9。
"""

from __future__ import annotations

import logging

import pytest

from ai_rpg_world.application.llm.wiring.feature_flags import (
    ENV_EPISODIC_EXPLORE_RELATED_ENABLED,
    log_episodic_explore_related_state,
    resolve_episodic_explore_related_enabled,
)


class TestResolveEpisodicExploreRelatedEnabled:
    """``EPISODIC_EXPLORE_RELATED_ENABLED`` の env パース。"""

    def test_env_未設定なら_default_OFF(self) -> None:
        """env 未設定なら OFF (検証中の default 不活性方針)。"""
        assert resolve_episodic_explore_related_enabled(env={}) is False

    def test_env_空文字なら_default_OFF(self) -> None:
        """空文字は未設定扱い → default OFF。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: ""}
        ) is False

    @pytest.mark.parametrize("raw", ["1", "true", "True", "TRUE", "yes", "YES", "on", "On"])
    def test_truthy_な値は_ON(self, raw: str) -> None:
        """truthy リテラル ("1", "true", "yes", "on") は case-insensitive で ON。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", "FALSE", "random", "2"])
    def test_falsy_または_未知の値は_OFF(self, raw: str) -> None:
        """truthy 以外は安全側 (OFF) に倒す。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: raw}
        ) is False

    def test_前後空白は_strip(self) -> None:
        """env var の値に空白混入があっても解釈できる。"""
        assert resolve_episodic_explore_related_enabled(
            env={ENV_EPISODIC_EXPLORE_RELATED_ENABLED: "  1  "}
        ) is True


class TestLogEpisodicExploreRelatedState:
    """解決状態を INFO ログ 1 件で残す (run 再現性確保用)。"""

    def test_ON_でも_OFF_でも_1件出る(self, caplog: pytest.LogCaptureFixture) -> None:
        """ENABLED / DISABLED の 2 ケースで INFO log が出る。"""
        with caplog.at_level(logging.INFO, logger="ai_rpg_world.application.llm.wiring.feature_flags"):
            log_episodic_explore_related_state(True)
            log_episodic_explore_related_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)
