"""item_specs に宣言した操作を world_graph の登録簿へ組み立てる境界を保証する。"""

from __future__ import annotations

import copy

import pytest

from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)
from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario


def _scenario_with_radio_interaction(*, effect: dict | None = None) -> dict:
    scenario = copy.deepcopy(_minimal_scenario())
    scenario["item_specs"] = [
        {
            "id": "portable_radio",
            "name": "携帯無線機",
            "description": "古い無線機",
            "category": "TOOL",
            "interactions": [
                {
                    "action_name": "hail_the_mainland",
                    "display_label": "応答を試す",
                    "preconditions": [],
                    "effects": [
                        effect
                        or {
                            "effect_type": "SHOW_MESSAGE",
                            "parameters": {"message": "雑音だけが返った。"},
                        }
                    ],
                }
            ],
        }
    ]
    # 元 fixture の item 参照を切り離し、道具 interaction だけを検査する。
    for spot in scenario["spots"]:
        for obj in spot.get("interior", {}).get("objects", []):
            obj["interactions"] = []
    scenario["connections"] = []
    return scenario


def test_item_interaction_is_registered_by_item_spec_id() -> None:
    """道具の操作は item ドメインではなく world_graph 側の登録簿に入る。"""
    loaded = ScenarioLoader().load_from_dict(_scenario_with_radio_interaction())
    item = loaded.item_spec_definitions[0]

    interactions = loaded.item_interaction_registry.interactions_for(item.spec_id)

    assert [entry.action_name for entry in interactions] == ["hail_the_mainland"]
    assert [entry.effective_display_label for entry in interactions] == ["応答を試す"]


_IMPLICIT_OBJECT_EFFECTS = (
    InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT,
    InteractionEffectTypeEnum.INCREMENT_OBJECT_STATE,
    InteractionEffectTypeEnum.CONSUME_OBJECT_STOCK,
    InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
    InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK,
    InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
    InteractionEffectTypeEnum.SHOW_PLAYER_TEXT,
)


@pytest.mark.parametrize("effect_type", _IMPLICIT_OBJECT_EFFECTS)
def test_item_interaction_rejects_an_implicit_object_effect(
    effect_type: InteractionEffectTypeEnum,
) -> None:
    """自身を暗黙対象にする物体効果は、対象物の無い道具操作では読み込み時に拒否する。"""
    effect = {
        "effect_type": effect_type.value,
        "parameters": {"state_key": "used", "quantity": 1},
    }
    if effect_type is InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT:
        effect["parameters"]["item_spec"] = "portable_radio"
    with pytest.raises(
        ScenarioLoadError,
        match=rf"item 'portable_radio'.*{effect_type.value}.*target_object",
    ):
        ScenarioLoader().load_from_dict(
            _scenario_with_radio_interaction(effect=effect)
        )


def test_item_interaction_accepts_an_explicit_object_target() -> None:
    """物体効果でも target_object を明示すれば道具操作へ宣言できる。"""
    scenario = _scenario_with_radio_interaction(
        effect={
            "effect_type": "INCREMENT_OBJECT_STATE",
            "parameters": {"target_object": "chest", "state_key": "signals"},
        }
    )
    # 参照先だけは残す。
    scenario["spots"][0]["interior"]["objects"][0]["interactions"] = []

    loaded = ScenarioLoader().load_from_dict(scenario)

    assert loaded.item_interaction_registry.interactions_for(
        loaded.item_spec_definitions[0].spec_id
    )[0].effects[0].parameters["object_id"] > 0


def test_item_interaction_loads_a_shared_cooldown_group() -> None:
    """道具の複数操作は cooldown_group を共有待ち時間のキーとして保持する。"""
    scenario = _scenario_with_radio_interaction()
    scenario["item_specs"][0]["interactions"][0]["cooldown_group"] = "radio"

    loaded = ScenarioLoader().load_from_dict(scenario)
    interaction = loaded.item_interaction_registry.interactions_for(
        loaded.item_spec_definitions[0].spec_id
    )[0]

    assert interaction.cooldown_group == "radio"
    assert interaction.cooldown_key == "radio"


def test_item_interaction_rejects_a_duplicate_action_name() -> None:
    """同じ品目の action_name 重複は最初の操作へ暗黙解決せず読み込み時に拒否する。"""
    scenario = _scenario_with_radio_interaction()
    interaction = copy.deepcopy(scenario["item_specs"][0]["interactions"][0])
    scenario["item_specs"][0]["interactions"].append(interaction)

    with pytest.raises(ScenarioLoadError, match="action_name 'hail_the_mainland' が重複"):
        ScenarioLoader().load_from_dict(scenario)


def test_item_without_interactions_keeps_an_empty_registry_entry() -> None:
    """既存の item_specs は interactions を持たなくても読み込み結果が変わらない。"""
    scenario = _scenario_with_radio_interaction()
    scenario["item_specs"][0].pop("interactions")

    loaded = ScenarioLoader().load_from_dict(scenario)

    assert loaded.item_interaction_registry.interactions_for(
        loaded.item_spec_definitions[0].spec_id
    ) == ()
