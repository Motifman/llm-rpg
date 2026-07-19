"""看板 (PR-F) の scenario JSON → VO 往復テスト。

WRITE_PLAYER_TEXT / SHOW_PLAYER_TEXT effect_type が JSON から
`InteractionEffect` へ正しく変換されることを、既存の `_minimal_scenario`
fixture に看板オブジェクトを追加する形で確認する。
"""

from __future__ import annotations

import copy

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader
from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario


def _scenario_with_sign() -> dict:
    scenario = copy.deepcopy(_minimal_scenario())
    scenario["spots"][0]["interior"]["objects"].append(
        {
            "id": "notice_board",
            "name": "掲示板",
            "description": "誰かが書き込めそうな掲示板。",
            "object_type": "SIGN",
            "state": {},
            "interactions": [
                {
                    "action_name": "write",
                    "display_label": "書き込む",
                    "preconditions": [],
                    "effects": [
                        {
                            "effect_type": "WRITE_PLAYER_TEXT",
                            "parameters": {},
                        }
                    ],
                },
                {
                    "action_name": "examine",
                    "display_label": "読む",
                    "preconditions": [],
                    "effects": [
                        {
                            "effect_type": "SHOW_PLAYER_TEXT",
                            "parameters": {},
                        }
                    ],
                },
            ],
        }
    )
    return scenario


class TestSignObjectScenarioLoading:
    """看板の JSON 定義が InteractionEffect まで正しく解決される。"""

    def test_write_player_text_effect_type_resolved(self) -> None:
        """write player text effect typeが解決される。"""
        result = ScenarioLoader().load_from_dict(_scenario_with_sign())
        for interior in result.interiors.values():
            for obj in interior.objects:
                if obj.name == "掲示板":
                    write_def = next(
                        i for i in obj.interactions if i.action_name == "write"
                    )
                    assert (
                        write_def.effects[0].effect_type
                        == InteractionEffectTypeEnum.WRITE_PLAYER_TEXT
                    )
                    return
        raise AssertionError("掲示板 object not found")

    def test_show_player_text_effect_type_resolved(self) -> None:
        """show player text effect typeが解決される。"""
        result = ScenarioLoader().load_from_dict(_scenario_with_sign())
        for interior in result.interiors.values():
            for obj in interior.objects:
                if obj.name == "掲示板":
                    examine_def = next(
                        i for i in obj.interactions if i.action_name == "examine"
                    )
                    assert (
                        examine_def.effects[0].effect_type
                        == InteractionEffectTypeEnum.SHOW_PLAYER_TEXT
                    )
                    return
        raise AssertionError("掲示板 object not found")

    def test_object_type_sign_preserved(self) -> None:
        """object type signが保持される。"""
        result = ScenarioLoader().load_from_dict(_scenario_with_sign())
        for interior in result.interiors.values():
            for obj in interior.objects:
                if obj.name == "掲示板":
                    from ai_rpg_world.domain.world_graph.enum.spot_object_type import (
                        SpotObjectTypeEnum,
                    )
                    assert obj.object_type == SpotObjectTypeEnum.SIGN
                    return
        raise AssertionError("掲示板 object not found")
