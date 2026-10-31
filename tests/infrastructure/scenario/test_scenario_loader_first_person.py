"""players[].first_person を読み込み、書かなければ一人称を決めないことを保証する (design_decisions D1469-3)。"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoader,
    ScenarioLoadError,
)


def _scenario_with_player(**fields: Any) -> dict[str, Any]:
    scenario = copy.deepcopy(_minimal_scenario())
    scenario["players"] = [{"id": "p1", "name": "ゲン", "spawn_spot": "room_a", "initial_items": [], **fields}]
    return scenario


class TestFirstPersonDeclaration:
    """first_person の宣言あり・なしで PlayerSpawnConfig が持つ値を保証する。"""

    def test_declared_first_person_is_kept_stripped(self) -> None:
        """first_person に書いた一人称は、前後の空白を落として持つ。"""
        result = ScenarioLoader().load_from_dict(_scenario_with_player(first_person=" 俺 "))

        assert result.player_spawns[0].first_person == "俺"

    def test_unspecified_first_person_is_none(self) -> None:
        """first_person を書かなければ None になり、仮の一人称を入れない。"""
        result = ScenarioLoader().load_from_dict(_scenario_with_player())

        assert result.player_spawns[0].first_person is None

    @pytest.mark.parametrize("value", ["", "   ", 1, None])
    def test_blank_or_non_text_first_person_is_rejected(self, value: object) -> None:
        """first_person に空白だけの文字列か文字列でない値を書くと、ScenarioLoadError で読み込みを止める。"""
        with pytest.raises(ScenarioLoadError, match="first_person"):
            ScenarioLoader().load_from_dict(_scenario_with_player(first_person=value))
