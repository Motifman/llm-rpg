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
    DEFAULT_SEMANTIC_PASSIVE_TOP_K,
    ENV_EPISODIC_EXPLORE_RELATED_ENABLED,
    ENV_SEMANTIC_PASSIVE_TOP_K,
    ENV_SEMANTIC_SEARCH_ENABLED,
    log_episodic_explore_related_state,
    log_semantic_passive_top_k_state,
    log_semantic_search_state,
    resolve_episodic_explore_related_enabled,
    resolve_semantic_passive_top_k,
    resolve_semantic_search_enabled,
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


class TestResolveSemanticPassiveTopK:
    """``SEMANTIC_PASSIVE_TOP_K`` env パース (Phase 1c)。"""

    def test_default_は_0(self) -> None:
        """default は 0 (= prompt §learned 非表示)。検証中の安定設定。"""
        assert DEFAULT_SEMANTIC_PASSIVE_TOP_K == 0
        assert resolve_semantic_passive_top_k(env={}) == 0

    def test_env_未設定なら_default_0(self) -> None:
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: ""}
        ) == 0

    def test_有効な正整数なら_その値(self) -> None:
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: "3"}
        ) == 3
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: "  5  "}
        ) == 5

    def test_0_なら_0_を返す(self) -> None:
        """明示的に 0 を渡しても受理。"""
        assert resolve_semantic_passive_top_k(
            env={ENV_SEMANTIC_PASSIVE_TOP_K: "0"}
        ) == 0

    def test_非数値なら_warning_log_を出して_default(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.wiring.feature_flags",
        ):
            v = resolve_semantic_passive_top_k(
                env={ENV_SEMANTIC_PASSIVE_TOP_K: "abc"}
            )
        assert v == 0
        assert any("non-integer" in rec.message for rec in caplog.records)

    def test_負数なら_warning_log_を出して_default(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.wiring.feature_flags",
        ):
            v = resolve_semantic_passive_top_k(
                env={ENV_SEMANTIC_PASSIVE_TOP_K: "-3"}
            )
        assert v == 0
        assert any("negative" in rec.message for rec in caplog.records)


class TestLogSemanticPassiveTopKState:
    """解決結果を INFO ログ 1 件で残す。"""

    def test_top_k_の値が_log_に_出る(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(
            logging.INFO,
            logger="ai_rpg_world.application.llm.wiring.feature_flags",
        ):
            log_semantic_passive_top_k_state(3)
            log_semantic_passive_top_k_state(0)
        assert any("3" in rec.message for rec in caplog.records)
        assert any("0" in rec.message for rec in caplog.records)


class TestResolveSemanticSearchEnabled:
    """``SEMANTIC_SEARCH_ENABLED`` env パース (Phase 1d)。"""

    def test_default_は_OFF(self) -> None:
        assert resolve_semantic_search_enabled(env={}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "ON", "True"])
    def test_truthy_は_ON(self, raw: str) -> None:
        assert resolve_semantic_search_enabled(
            env={ENV_SEMANTIC_SEARCH_ENABLED: raw}
        ) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", "random", ""])
    def test_falsy_または_未知の値は_OFF(self, raw: str) -> None:
        assert resolve_semantic_search_enabled(
            env={ENV_SEMANTIC_SEARCH_ENABLED: raw}
        ) is False


class TestLogSemanticSearchState:
    """解決結果を INFO ログ 1 件で残す (Phase 1d)。"""

    def test_ENABLED_でも_DISABLED_でも_log_に_出る(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(
            logging.INFO,
            logger="ai_rpg_world.application.llm.wiring.feature_flags",
        ):
            log_semantic_search_state(True)
            log_semantic_search_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("ENABLED" in m for m in messages)
        assert any("DISABLED" in m for m in messages)
