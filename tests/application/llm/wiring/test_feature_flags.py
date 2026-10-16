"""``wiring/feature_flags.py`` の env-driven knob 解決テスト。"""

from __future__ import annotations

import logging

import pytest

from ai_rpg_world.application.llm.wiring.feature_flags import (
    ENV_MEMO_TOOLS_ENABLED,
    log_memo_tools_enabled_state,
    resolve_memo_tools_enabled,
)


class TestResolveMemoToolsEnabled:
    """``MEMO_TOOLS_ENABLED`` の env パース。"""

    def test_env_unset_default_on(self) -> None:
        """env 未設定なら既存 run 互換で memo tool を露出する。"""
        assert resolve_memo_tools_enabled(env={}) is True

    @pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on"])
    def test_truthy_value_on(self, raw: str) -> None:
        """truthy な値は memo tool 露出 ON。"""
        assert resolve_memo_tools_enabled(env={ENV_MEMO_TOOLS_ENABLED: raw}) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_falsy_value_off(self, raw: str) -> None:
        """falsy な値は memo tool 露出 OFF。"""
        assert resolve_memo_tools_enabled(env={ENV_MEMO_TOOLS_ENABLED: raw}) is False

    def test_unknown_raises_value_error(self) -> None:
        """未知の値は ValueError で落とし、実験 profile の typo を黙って受けない。"""
        with pytest.raises(ValueError):
            resolve_memo_tools_enabled(env={ENV_MEMO_TOOLS_ENABLED: "maybe"})

    def test_log_state_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """log state はレベル情報でログを出す。"""
        with caplog.at_level(logging.INFO):
            log_memo_tools_enabled_state(True)
            log_memo_tools_enabled_state(False)
        messages = [rec.message for rec in caplog.records]
        assert any("MEMO_TOOLS_ENABLED" in m for m in messages)

