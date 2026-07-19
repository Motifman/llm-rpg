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

    def test_unspecified_witness_policy_defaults_to_same_spot(self) -> None:
        """未指定なら SAME SPOT。"""
        idef = _load_first_interaction(_scenario_with_interaction({}))
        assert idef.witness_policy is WitnessPolicy.SAME_SPOT


class TestWitnessPolicyExplicit:
    """明示宣言で正しく enum に変換される。"""

    def test_actor_only_string(self) -> None:
        """ACTORONLY を文字列で宣言できる。"""
        idef = _load_first_interaction(_scenario_with_interaction({
            "witness_policy": "ACTOR_ONLY",
        }))
        assert idef.witness_policy is WitnessPolicy.ACTOR_ONLY

    def test_same_spot_witness_policy_can_be_declared_explicitly(self) -> None:
        """明示しても default と同じ結果。"""
        idef = _load_first_interaction(_scenario_with_interaction({
            "witness_policy": "SAME_SPOT",
        }))
        assert idef.witness_policy is WitnessPolicy.SAME_SPOT


class TestWitnessPolicyValidation:
    """typo や型エラーを boundary で弾く。"""

    def test_unknown_value_scenario_load_error(self) -> None:
        """未知の値は ScenarioLoadError。"""
        with pytest.raises(ScenarioLoadError, match="witness_policy must be one of"):
            _load_first_interaction(_scenario_with_interaction({
                "witness_policy": "EVERYONE",
            }))

    def test_string_scenario_load_error(self) -> None:
        """文字列以外なら ScenarioLoadError。"""
        with pytest.raises(ScenarioLoadError, match="witness_policy must be a string"):
            _load_first_interaction(_scenario_with_interaction({
                "witness_policy": 1,
            }))
