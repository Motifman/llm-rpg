"""players[].initial_gold のパースと fail-fast 検証 (経済統合 Phase 0)。

所持金の初期値をシナリオが宣言できるようにする。この PR では
``PlayerSpawnConfig`` への保持までを担い、``PlayerStatusAggregate`` への配線は
売買ツールを入れる PR で行う。
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


def _scenario_with_initial_gold(value: Any, *, omit: bool = False) -> Dict[str, Any]:
    """最小シナリオの唯一のプレイヤーへ initial_gold を差し込んだ raw dict を返す。"""
    scenario = copy.deepcopy(_minimal_scenario())
    if not omit:
        scenario["players"][0]["initial_gold"] = value
    return scenario


class TestInitialGoldDeclaration:
    """initial_gold の宣言あり・なしで PlayerSpawnConfig が保持する値を保証する。"""

    def test_unspecified_initial_gold_defaults_to_zero(self) -> None:
        """initial_gold を書かないプレイヤーの所持金初期値は 0 になる。"""
        result = ScenarioLoader().load_from_dict(_scenario_with_initial_gold(None, omit=True))

        assert result.player_spawns[0].initial_gold == 0

    def test_declared_initial_gold_is_kept(self) -> None:
        """initial_gold に正の整数を書くと、その値がそのまま保持される。"""
        result = ScenarioLoader().load_from_dict(_scenario_with_initial_gold(120))

        assert result.player_spawns[0].initial_gold == 120

    def test_zero_initial_gold_is_accepted(self) -> None:
        """initial_gold に 0 を明示しても受理される (無一文で始まる宣言)。"""
        result = ScenarioLoader().load_from_dict(_scenario_with_initial_gold(0))

        assert result.player_spawns[0].initial_gold == 0


class TestInitialGoldValidation:
    """initial_gold の誤記を読み込み時に落とす。"""

    def test_negative_initial_gold_is_rejected(self) -> None:
        """initial_gold が負値のとき ScenarioLoadError を投げる (Gold は下限 0 のため)。"""
        with pytest.raises(ScenarioLoadError, match="initial_gold"):
            ScenarioLoader().load_from_dict(_scenario_with_initial_gold(-1))

    @pytest.mark.parametrize("value", ["100", 10.5, True, [10]])
    def test_non_integer_initial_gold_is_rejected(self, value: Any) -> None:
        """initial_gold が整数でないとき (文字列・小数・真偽値・配列) ScenarioLoadError を投げる。"""
        with pytest.raises(ScenarioLoadError, match="initial_gold"):
            ScenarioLoader().load_from_dict(_scenario_with_initial_gold(value))
