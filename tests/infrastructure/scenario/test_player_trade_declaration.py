"""エージェント同士の取引を使う世界かの宣言 (経済統合 Phase 2)。

商人 (merchants) とは別の宣言にする。商人の居る町でも「人同士の取引は
しない」世界はありえるし、逆もある。宣言の無い世界では取引ツールを出さず、
既存 run の tool 一覧を動かさない。
"""

from __future__ import annotations

import copy
from typing import Any, Dict

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)
from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario


def _scenario_with(block: Any) -> Dict[str, Any]:
    scenario = copy.deepcopy(_minimal_scenario())
    scenario["player_trade"] = block
    return scenario


class TestPlayerTradeDeclaration:
    """player_trade block の有無と enabled から取引機構の on/off が決まる。"""

    def test_it_is_off_when_undeclared(self) -> None:
        """宣言の無いシナリオでは、エージェント同士の取引は無効になる。"""
        result = ScenarioLoader().load_from_dict(_minimal_scenario())

        assert result.player_trade_enabled is False

    def test_declaring_the_block_turns_it_on(self) -> None:
        """block を書いただけで有効になる (書いたのに効かない状態を作らない)。"""
        result = ScenarioLoader().load_from_dict(_scenario_with({}))

        assert result.player_trade_enabled is True

    def test_it_can_be_turned_off_explicitly(self) -> None:
        """enabled: false と明示すれば無効にできる。"""
        result = ScenarioLoader().load_from_dict(_scenario_with({"enabled": False}))

        assert result.player_trade_enabled is False

    def test_a_non_object_block_is_rejected(self) -> None:
        """player_trade がオブジェクトでないとき ScenarioLoadError を投げる。"""
        with pytest.raises(ScenarioLoadError, match="player_trade"):
            ScenarioLoader().load_from_dict(_scenario_with(True))

    @pytest.mark.parametrize("value", ["true", 1, None])
    def test_a_non_boolean_enabled_is_rejected(self, value: Any) -> None:
        """enabled が真偽値でないとき ScenarioLoadError を投げる。"""
        with pytest.raises(ScenarioLoadError, match="enabled"):
            ScenarioLoader().load_from_dict(_scenario_with({"enabled": value}))

    def test_it_is_independent_from_the_merchant_declaration(self) -> None:
        """商人の宣言とは独立している (片方だけを宣言できる)。"""
        scenario = _scenario_with({})
        scenario["merchants"] = []

        result = ScenarioLoader().load_from_dict(scenario)

        assert result.player_trade_enabled is True
        assert result.merchants == ()
