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

    def test_unset_default_6(self) -> None:
        """未設定なら 6 tick (#346 Step 3 既定)。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.llm_idle_timeout_ticks == 6

    def test_config_24(self) -> None:
        """1 日 (24 tick) 沈黙許容を試したい場合の長め設定。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={"LLM_IDLE_TIMEOUT_TICKS": "24"}
        )
        assert cfg.llm_idle_timeout_ticks == 24

    def test_config_can_lower_idle_timeout_to_one(self) -> None:
        """旧 heartbeat 並の頻発を再現したい場合の最小値。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={"LLM_IDLE_TIMEOUT_TICKS": "1"}
        )
        assert cfg.llm_idle_timeout_ticks == 1

    def test_case_raises_value_error(self) -> None:
        """parse 失敗は既定値縮退ではなく profile ミスとして止める。"""
        with pytest.raises(ValueError, match="LLM_IDLE_TIMEOUT_TICKS"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_IDLE_TIMEOUT_TICKS": "abc"}
            )

    def test_zero_raises_value_error(self) -> None:
        """0 / 負値は heartbeat emitter に渡す前に fail-fast する。"""
        with pytest.raises(ValueError, match="LLM_IDLE_TIMEOUT_TICKS"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_IDLE_TIMEOUT_TICKS": "0"}
            )
        with pytest.raises(ValueError, match="LLM_IDLE_TIMEOUT_TICKS"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_IDLE_TIMEOUT_TICKS": "-5"}
            )


class TestResolveLlmToolChoice:
    """LLM_TOOL_CHOICE は required / auto だけを受理し、実効設定を trace 化する。"""

    def test_required_is_the_default(self) -> None:
        """未指定なら既存契約の required を保ち、プロンプト挙動を変えない。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})

        assert cfg.llm_tool_choice == "required"
        assert cfg.to_trace_dict()["llm_tool_choice"] == "required"

    def test_auto_disables_reason_first_in_the_resolved_config(self) -> None:
        """auto では対応未確認の named tool_choice を使う reason-first を実効無効にする。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={
                "LLM_TOOL_CHOICE": "auto",
                "REASON_FIRST_TWO_STEP_ENABLED": "true",
            }
        )

        assert cfg.llm_tool_choice == "auto"
        assert cfg.reason_first_two_step_enabled is False
        assert cfg.to_trace_dict()["reason_first_two_step_enabled"] is False

    @pytest.mark.parametrize("value", ["sometimes", "required 或 auto"])
    def test_unknown_values_fail_fast(self, value: str) -> None:
        """未知の tool_choice は run 開始前に ValueError で拒否する。"""
        with pytest.raises(ValueError, match="LLM_TOOL_CHOICE"):
            ResolvedLlmRuntimeConfig.from_mapping(values={"LLM_TOOL_CHOICE": value})


class TestResolveLlmSessionIdEnabled:
    """LLM_SESSION_ID_ENABLED は sticky routing の送信有無を厳密に解決する。"""

    def test_session_id_is_enabled_by_default(self) -> None:
        """未指定なら既存挙動を保ち、解決済み設定にも true を残す。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})

        assert cfg.llm_session_id_enabled is True
        assert cfg.to_trace_dict()["llm_session_id_enabled"] is True

    def test_false_disables_session_id(self) -> None:
        """false は空文字への変換ではなく、会話 ID の送信自体を無効にする。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={"LLM_SESSION_ID_ENABLED": "false"}
        )

        assert cfg.llm_session_id_enabled is False

    @pytest.mark.parametrize("value", ["sticky", "sometimes"])
    def test_unknown_values_fail_fast(self, value: str) -> None:
        """未知値は true への縮退を許さず、run の開始前に拒否する。"""
        with pytest.raises(ValueError, match="LLM_SESSION_ID_ENABLED"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_SESSION_ID_ENABLED": value}
            )
