"""予期の清算の有効化と上限を profile から入れ、組めない設定を起動前に落とす (#1440)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)

_ON = {
    "TYPED_JUDGMENT_PROVIDER": "stub",
    "EXPECTATION_SETTLEMENT_ENABLED": "1",
}


def _config(**values: str) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.from_mapping(values=values)


class TestTheProfileChoosesTheSettlement:
    """有効化と 3 つの上限が profile から入り、run_start の記録に残ることを保証する。"""

    def test_settlement_is_off_unless_the_profile_asks_for_it(self) -> None:
        """何も書かなければ清算は無効で、上限は 1 以上の既定値になる。"""
        config = _config()

        assert config.expectation_settlement_enabled is False
        assert config.expectation_settlement_max_open >= 1
        assert config.expectation_settlement_timeline_turns >= 1
        assert config.expectation_event_max_delivery_attempts >= 1

    def test_the_profile_sets_the_limits_and_they_reach_run_start(self) -> None:
        """上限を書くと解決済み設定に載り、run_start に残る trace 表現にも出る。"""
        config = _config(
            **_ON,
            EXPECTATION_SETTLEMENT_MAX_OPEN="5",
            EXPECTATION_SETTLEMENT_TIMELINE_TURNS="2",
            EXPECTATION_EVENT_MAX_DELIVERY_ATTEMPTS="4",
        )

        trace = config.to_trace_dict()
        assert trace["expectation_settlement_enabled"] is True
        assert trace["expectation_settlement_max_open"] == 5
        assert trace["expectation_settlement_timeline_turns"] == 2
        assert trace["expectation_event_max_delivery_attempts"] == 4


class TestUnusableSettingsFailBeforeTheRun:
    """組めない設定を run の前に ValueError で落とすことを保証する。"""

    def test_enabling_without_a_judgment_provider_fails(self) -> None:
        """判断の provider が off のまま清算を有効にすると、問う先が無いので ValueError を投げる。"""
        with pytest.raises(ValueError, match="EXPECTATION_SETTLEMENT_ENABLED"):
            _config(EXPECTATION_SETTLEMENT_ENABLED="1")

    @pytest.mark.parametrize(
        "key",
        [
            "EXPECTATION_SETTLEMENT_MAX_OPEN",
            "EXPECTATION_SETTLEMENT_TIMELINE_TURNS",
            "EXPECTATION_EVENT_MAX_DELIVERY_ATTEMPTS",
        ],
    )
    def test_non_positive_limit_fails(self, key: str) -> None:
        """上限に 0 を書くと ValueError を投げる。"""
        with pytest.raises(ValueError, match=key):
            _config(**_ON, **{key: "0"})
