"""シナリオ直下 player_interactions のパースを保証する。

対人行為 (奪う・手当てする・印を刻む) の定義はシナリオに 1 回だけ書き、
「どこで使えるか」は前提条件で表現する。spot object にぶら下げると同じ行為を
複数の場所で使うのに複数回定義が要り、「暗い場所ならどこでも」のような動的な
条件も書けない (docs/memory_system/interpersonal_interaction_design.md §3.2)。
"""

from __future__ import annotations

import copy

import pytest

from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


def _scenario_with_player_interactions(*defs: dict) -> dict:
    from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

    scenario = copy.deepcopy(_minimal_scenario())
    scenario["player_interactions"] = list(defs)
    return scenario


def _take_def(**overrides) -> dict:
    base = {
        "action_name": "take",
        "display_label": "持ち物を奪う",
        "preconditions": [
            {
                "condition_type": "TARGET_PLAYER_IS_INCAPACITATED",
                "failure_message": "相手は起きている。奪えない。",
            }
        ],
        "effects": [
            {
                "effect_type": "REMOVE_ITEM",
                "target": "TARGET_PLAYER",
                "parameters": {"from_parameter": "item_label"},
            }
        ],
    }
    base.update(overrides)
    return base


class TestPlayerInteractionsParsing:
    """シナリオ直下の player_interactions が読み込まれる。"""

    def test_absent_key_yields_empty_tuple(self) -> None:
        """player_interactions を書かないシナリオでは空タプルになる (既存シナリオは不変)。"""
        from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

        result = ScenarioLoader().load_from_dict(copy.deepcopy(_minimal_scenario()))
        assert result.player_interactions == ()

    def test_action_name_and_label_are_parsed(self) -> None:
        """action_name と display_label がそのまま載る。"""
        result = ScenarioLoader().load_from_dict(
            _scenario_with_player_interactions(_take_def())
        )
        assert len(result.player_interactions) == 1
        idef = result.player_interactions[0]
        assert idef.action_name == "take"
        assert idef.display_label == "持ち物を奪う"

    def test_effect_target_player_is_allowed_here(self) -> None:
        """player_interactions の効果には target=TARGET_PLAYER を書ける。

        行為者と対象がどちらも存在する唯一の文脈なので、scenario_event などと
        違って拒否しない。
        """
        result = ScenarioLoader().load_from_dict(
            _scenario_with_player_interactions(_take_def())
        )
        effect = result.player_interactions[0].effects[0]
        assert effect.target is EffectTarget.TARGET_PLAYER

    def test_duplicate_action_name_fails_to_load(self) -> None:
        """同じ action_name を 2 つ書くと ScenarioLoadError になる。

        LLM は action_name で行為を指定するので、重複すると「どちらが実行されたか
        分からない」状態になる。
        """
        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader().load_from_dict(
                _scenario_with_player_interactions(_take_def(), _take_def())
            )
        assert "take" in str(exc_info.value)

    def test_missing_action_name_fails_to_load(self) -> None:
        """action_name の無い定義は ScenarioLoadError になる。"""
        broken = _take_def()
        del broken["action_name"]
        with pytest.raises(ScenarioLoadError):
            ScenarioLoader().load_from_dict(
                _scenario_with_player_interactions(broken)
            )

    def test_effect_without_target_player_fails_to_load(self) -> None:
        """対象への効果を 1 つも持たない定義は ScenarioLoadError になる。

        player_interactions は「相手に何かをする」ための宣言なので、行為者にしか
        効かない定義は書き間違いとみなす。放置すると「相手を選んだのに自分に
        効く」という最も分かりにくい失敗になる。
        """
        actor_only = _take_def(
            effects=[
                {"effect_type": "APPLY_DAMAGE", "parameters": {"damage": 1}}
            ]
        )
        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader().load_from_dict(
                _scenario_with_player_interactions(actor_only)
            )
        assert "TARGET_PLAYER" in str(exc_info.value)
