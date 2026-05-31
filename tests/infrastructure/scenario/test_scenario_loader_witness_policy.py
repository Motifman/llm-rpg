"""interactions[].witness_policy のパース検証 (Phase G #1)。

JSON で "witness_policy": "ACTOR_ONLY" を宣言したとき、loader が
InteractionDef.witness_policy に正しく載せること、不正値・型エラーを
弾くこと、デフォルトが SAME_SPOT であることを確認する。
"""

from __future__ import annotations

import copy

import pytest

from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


def _scenario_with_interaction(action_overrides: dict) -> dict:
    """最小シナリオの 1 interaction を差し替える。"""
    from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario
    scenario = copy.deepcopy(_minimal_scenario())
    base_action = scenario["spots"][0]["interior"]["objects"][0]["interactions"][0]
    base_action.update(action_overrides)
    return scenario


def _load_first_interaction(scenario: dict):
    result = ScenarioLoader().load_from_dict(scenario)
    interior = result.interiors[next(iter(result.interiors))]
    return interior.objects[0].interactions[0]


class TestWitnessPolicyDefault:
    """既存シナリオ (witness_policy 未指定) は default SAME_SPOT。"""

    def test_未指定なら_SAME_SPOT(self) -> None:
        idef = _load_first_interaction(_scenario_with_interaction({}))
        assert idef.witness_policy is WitnessPolicy.SAME_SPOT


class TestWitnessPolicyExplicit:
    """明示宣言で正しく enum に変換される。"""

    def test_ACTOR_ONLY_を_文字列で宣言できる(self) -> None:
        idef = _load_first_interaction(_scenario_with_interaction({
            "witness_policy": "ACTOR_ONLY",
        }))
        assert idef.witness_policy is WitnessPolicy.ACTOR_ONLY

    def test_SAME_SPOT_を_明示宣言できる(self) -> None:
        """明示しても default と同じ結果。"""
        idef = _load_first_interaction(_scenario_with_interaction({
            "witness_policy": "SAME_SPOT",
        }))
        assert idef.witness_policy is WitnessPolicy.SAME_SPOT


class TestWitnessPolicyValidation:
    """typo や型エラーを boundary で弾く。"""

    def test_未知の値は_ScenarioLoadError(self) -> None:
        with pytest.raises(ScenarioLoadError, match="witness_policy must be one of"):
            _load_first_interaction(_scenario_with_interaction({
                "witness_policy": "EVERYONE",
            }))

    def test_文字列以外なら_ScenarioLoadError(self) -> None:
        with pytest.raises(ScenarioLoadError, match="witness_policy must be a string"):
            _load_first_interaction(_scenario_with_interaction({
                "witness_policy": 1,
            }))
