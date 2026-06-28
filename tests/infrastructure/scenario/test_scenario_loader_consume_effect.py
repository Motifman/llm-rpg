"""scenario_loader が consume_effect を ItemEffect に変換する (Phase F)。

JSON の単一 dict / list / 未指定の各形式と、未知 type / 必須欠落のエラーを
確認する。loader 単体のユニットテストなので最小シナリオで足りる。
"""

from __future__ import annotations

import copy

import pytest

from ai_rpg_world.domain.item.value_object.item_effect import (
    CompositeItemEffect,
    HealEffect,
    ReviveEffect,
    SatisfyNeedEffect,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader


def _scenario_with_item(item_dict: dict) -> dict:
    """consume_effect 検証用の最小シナリオ。既存テストの `_minimal_scenario` の
    item_specs だけを差し替える。"""
    from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario
    scenario = copy.deepcopy(_minimal_scenario())
    scenario["item_specs"] = [item_dict]
    # GIVE_ITEM の参照は wood/water/fish などに合わせて消す (item_specs を
    # 差し替えるので key 参照が破綻するため)。
    for spot in scenario.get("spots", []):
        interior = spot.get("interior", {})
        for obj in interior.get("objects", []):
            obj["interactions"] = []
    scenario["connections"] = []
    return scenario


def _load_first_item(scenario_dict: dict):
    result = ScenarioLoader().load_from_dict(scenario_dict)
    return result.item_spec_definitions[0]


class TestConsumeEffectParsing:
    """JSON shape ごとのパース挙動。"""

    def test_consume_effect_未指定なら_None(self) -> None:
        item_def = _load_first_item(_scenario_with_item(
            {"id": "wood", "name": "木", "description": "ただの木", "category": "MATERIAL"}
        ))
        assert item_def.consume_effect is None

    def test_単一_dict_は_単一_ItemEffect_に解決される(self) -> None:
        item_def = _load_first_item(_scenario_with_item(
            {
                "id": "water", "name": "水", "description": "飲み水", "category": "FOOD",
                "consume_effect": {"type": "heal_hp", "amount": 3},
            }
        ))
        assert isinstance(item_def.consume_effect, HealEffect)
        assert item_def.consume_effect.amount == 3

    def test_list_は_CompositeItemEffect_に解決される(self) -> None:
        item_def = _load_first_item(_scenario_with_item(
            {
                "id": "fish", "name": "魚", "description": "魚", "category": "FOOD",
                "consume_effect": [
                    {"type": "heal_hp", "amount": 5},
                    {"type": "satisfy_need", "need_type": "HUNGER", "amount": 30},
                ],
            }
        ))
        eff = item_def.consume_effect
        assert isinstance(eff, CompositeItemEffect)
        assert len(eff.effects) == 2
        assert isinstance(eff.effects[0], HealEffect)
        assert isinstance(eff.effects[1], SatisfyNeedEffect)
        assert eff.effects[1].need_type_name == "HUNGER"
        assert eff.effects[1].amount == 30

    def test_要素1個の_list_は_単一_ItemEffect_になる(self) -> None:
        item_def = _load_first_item(_scenario_with_item(
            {
                "id": "berry", "name": "実", "description": "実", "category": "FOOD",
                "consume_effect": [{"type": "heal_hp", "amount": 2}],
            }
        ))
        # 要素1個は Composite ではなく単体で返す (冗長な wrap を避ける)
        assert isinstance(item_def.consume_effect, HealEffect)


class TestConsumeEffectValidation:
    """エラー条件: 未知 type / 必須欠落。"""

    def test_未知の_type_は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="unknown consume_effect type"):
            _load_first_item(_scenario_with_item(
                {
                    "id": "x", "name": "x", "description": "x", "category": "FOOD",
                    "consume_effect": {"type": "teleport", "amount": 1},
                }
            ))

    def test_satisfy_need_の_need_type_欠落で_ValueError(self) -> None:
        with pytest.raises(ValueError, match="satisfy_need requires"):
            _load_first_item(_scenario_with_item(
                {
                    "id": "x", "name": "x", "description": "x", "category": "FOOD",
                    "consume_effect": {"type": "satisfy_need", "amount": 10},
                }
            ))

    def test_type_欠落で_ValueError(self) -> None:
        with pytest.raises(ValueError, match="missing 'type'"):
            _load_first_item(_scenario_with_item(
                {
                    "id": "x", "name": "x", "description": "x", "category": "FOOD",
                    "consume_effect": {"amount": 5},
                }
            ))


class TestReviveEffectParsing:
    """Issue #621 Phase 3a: `revive` type の consume_effect parse。"""

    def test_revive_単一_dict_で_ReviveEffect_に_解決される(self) -> None:
        item_def = _load_first_item(_scenario_with_item(
            {
                "id": "first_aid", "name": "救急用品",
                "description": "蘇生薬", "category": "CONSUMABLE",
                "consume_effect": {"type": "revive", "hp_rate": 0.4},
            }
        ))
        assert isinstance(item_def.consume_effect, ReviveEffect)
        assert item_def.consume_effect.hp_rate == 0.4

    def test_revive_と_heal_の_合成も_可能(self) -> None:
        """蘇生 + 追加 HP 回復のような composite。"""
        item_def = _load_first_item(_scenario_with_item(
            {
                "id": "high_aid", "name": "高級救急用品",
                "description": "蘇生+HP回復", "category": "CONSUMABLE",
                "consume_effect": [
                    {"type": "revive", "hp_rate": 0.4},
                    {"type": "heal_hp", "amount": 20},
                ],
            }
        ))
        eff = item_def.consume_effect
        assert isinstance(eff, CompositeItemEffect)
        assert isinstance(eff.effects[0], ReviveEffect)
        assert eff.effects[0].hp_rate == 0.4
        assert isinstance(eff.effects[1], HealEffect)

    def test_revive_の_hp_rate_未指定で_ValueError(self) -> None:
        with pytest.raises((KeyError, ValueError)):
            _load_first_item(_scenario_with_item(
                {
                    "id": "x", "name": "x", "description": "x", "category": "CONSUMABLE",
                    "consume_effect": {"type": "revive"},
                }
            ))

    def test_revive_の_hp_rate_範囲外で_例外(self) -> None:
        """ReviveEffect の __post_init__ が ItemEffectValidationException を投げる。"""
        from ai_rpg_world.domain.item.exception import ItemEffectValidationException
        with pytest.raises(ItemEffectValidationException):
            _load_first_item(_scenario_with_item(
                {
                    "id": "x", "name": "x", "description": "x", "category": "CONSUMABLE",
                    "consume_effect": {"type": "revive", "hp_rate": 1.5},
                }
            ))
