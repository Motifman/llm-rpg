"""ScenarioLoader が interaction の display_label 欠落を読み込み時に弾くことを保証する。"""

from __future__ import annotations

import copy

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)
from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario


def _scenario_with_object_interaction(action_overrides: dict, *, remove_label: bool = False) -> dict:
    """最小シナリオの object interaction を差し替える。"""
    scenario = copy.deepcopy(_minimal_scenario())
    action = scenario["spots"][0]["interior"]["objects"][0]["interactions"][0]
    if remove_label:
        action.pop("display_label", None)
    action.update(action_overrides)
    return scenario


def _scenario_with_player_interaction(action_overrides: dict, *, remove_label: bool = False) -> dict:
    """最小シナリオに player_interaction を追加し、必要なら display_label を欠落させる。"""
    scenario = copy.deepcopy(_minimal_scenario())
    action = {
        "action_name": "loot_from_downed",
        "display_label": "持ち物を奪う",
        "preconditions": [],
        "effects": [],
    }
    if remove_label:
        action.pop("display_label", None)
    action.update(action_overrides)
    scenario["player_interactions"] = [action]
    return scenario


class TestObjectInteractionDisplayLabelValidation:
    """object interaction の display_label 欠落・空白を ScenarioLoadError にする。"""

    def test_missing_display_label_raises_scenario_load_error(self) -> None:
        """display_label 欠落は KeyError ではなく、修正位置が分かる ScenarioLoadError。"""
        with pytest.raises(ScenarioLoadError, match=r"interaction\['open'\].display_label"):
            ScenarioLoader().load_from_dict(
                _scenario_with_object_interaction({}, remove_label=True)
            )

    def test_blank_display_label_raises_scenario_load_error(self) -> None:
        """空白だけの display_label は、裸の action_name 表示へ戻るので拒否する。"""
        with pytest.raises(
            ScenarioLoadError,
            match=r"interaction\['open'\].display_label must be a non-empty string",
        ):
            ScenarioLoader().load_from_dict(
                _scenario_with_object_interaction({"display_label": "  "})
            )


class TestPlayerInteractionDisplayLabelValidation:
    """player_interaction の display_label 欠落・空白も同じ境界で止める。"""

    def test_missing_display_label_raises_scenario_load_error(self) -> None:
        """対人 action でも display_label 欠落は ScenarioLoadError。"""
        with pytest.raises(
            ScenarioLoadError,
            match=r"interaction\['loot_from_downed'\].display_label",
        ):
            ScenarioLoader().load_from_dict(
                _scenario_with_player_interaction({}, remove_label=True)
            )

    def test_blank_display_label_raises_scenario_load_error(self) -> None:
        """対人 action でも空白 display_label は拒否する。"""
        with pytest.raises(
            ScenarioLoadError,
            match=(
                r"interaction\['loot_from_downed'\].display_label "
                r"must be a non-empty string"
            ),
        ):
            ScenarioLoader().load_from_dict(
                _scenario_with_player_interaction({"display_label": ""})
            )
