"""players[].knows_at_start のパースと読み込み時の検証 (#1520)。"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoader,
    ScenarioLoadError,
)


def _three_players(knows_at_start: Any = None, *, omit: bool = False) -> dict[str, Any]:
    """最小シナリオを 3 人にし、p1 に knows_at_start を差し込んだ raw dict を返す。"""
    scenario = copy.deepcopy(_minimal_scenario())
    scenario["players"] = [
        {"id": "p1", "name": "エイダ", "spawn_spot": "room_a", "initial_items": [], "appearance": "外套の女"},
        {"id": "p2", "name": "ノア", "spawn_spot": "room_a", "initial_items": [], "appearance": "背の高い男"},
        {"id": "p3", "name": "カイ", "spawn_spot": "room_b", "initial_items": [], "appearance": "赤い頭巾の人"},
    ]
    if not omit:
        scenario["players"][0]["knows_at_start"] = knows_at_start
    return scenario


class TestKnowsAtStartDeclaration:
    """knows_at_start の宣言あり・なしで PlayerSpawnConfig が保持する値を保証する。"""

    def test_unspecified_means_none(self) -> None:
        """knows_at_start を書かないプレイヤーは None (全員を紹介する) になる。"""
        result = ScenarioLoader().load_from_dict(_three_players(omit=True))

        assert result.player_spawns[0].knows_at_start is None

    def test_declared_ids_are_kept_in_order(self) -> None:
        """knows_at_start に書いた player id は、書いた順の tuple で保持される。"""
        result = ScenarioLoader().load_from_dict(_three_players(["p3", "p2"]))

        assert result.player_spawns[0].knows_at_start == ("p3", "p2")

    def test_empty_list_is_kept_as_empty(self) -> None:
        """空の配列は「誰も紹介しない」として空の tuple で保持され、None と区別される。"""
        result = ScenarioLoader().load_from_dict(_three_players([]))

        assert result.player_spawns[0].knows_at_start == ()


class TestKnowsAtStartValidation:
    """knows_at_start の書き間違いを読み込み時に止めることを保証する。"""

    @pytest.mark.parametrize(
        "value",
        [
            "p2",
            ["p9"],
            ["p1"],
            ["p2", "p2"],
            [2],
            None,
        ],
        ids=["not_list", "unknown", "self", "duplicate", "not_str", "null"],
    )
    def test_invalid_declaration_is_rejected(self, value: Any) -> None:
        """配列でない・居ない id・自分・重複・文字列でない・null を書くと ScenarioLoadError を投げる。"""
        with pytest.raises(ScenarioLoadError, match="knows_at_start"):
            ScenarioLoader().load_from_dict(_three_players(value))
