"""Phase 2-A — アイテム数量セマンティクスのユニットテスト。

GIVE_ITEM / REMOVE_ITEM の quantity パラメータと、
HAS_ITEM / HAS_ITEMS precondition の required_quantity パラメータを
それぞれ検証する。default は従来挙動 (1 個) と互換であることも確認する。
"""

from __future__ import annotations

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _empty_interior() -> SpotInterior:
    return SpotInterior((), (), (), ())


class TestGiveItemQuantity:
    """GIVE_ITEM effect の quantity パラメータ。"""

    def test_default_quantity_is_one(self) -> None:
        """quantity を渡さなければ従来通り 1 個分の grant が出る。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
            parameters={"item_spec_id": 7},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.item_spec_ids_to_grant) == 1
        assert result.item_spec_ids_to_grant[0] == ItemSpecId.create(7)

    def test_quantity_n_grants_n_instances(self) -> None:
        """quantity=3 なら同じ spec が 3 回 grant に積まれる。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
            parameters={"item_spec_id": 7, "quantity": 3},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.item_spec_ids_to_grant) == 3
        assert all(sid == ItemSpecId.create(7) for sid in result.item_spec_ids_to_grant)

    def test_negative_quantity_yields_zero_grants(self) -> None:
        """負の quantity は 0 にクランプして安全に no-op にする。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
            parameters={"item_spec_id": 7, "quantity": -2},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert result.item_spec_ids_to_grant == ()

    def test_zero_quantity_yields_no_grant(self) -> None:
        """quantity=0 でも安全に no-op (grant なし)。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
            parameters={"item_spec_id": 7, "quantity": 0},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert result.item_spec_ids_to_grant == ()

    def test_invalid_quantity_string_falls_back_to_one(self) -> None:
        """quantity に不正な値が来た場合は default=1 にフォールバック。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
            parameters={"item_spec_id": 7, "quantity": "not-an-int"},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.item_spec_ids_to_grant) == 1


class TestRemoveItemQuantity:
    """REMOVE_ITEM effect の quantity パラメータ。"""

    def test_quantity_n_queues_n_removals(self) -> None:
        """quantity=2 なら 2 回 remove リストに積まれる。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.REMOVE_ITEM,
            parameters={"item_spec_id": 7, "quantity": 2},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.item_spec_ids_to_remove) == 2

    def test_default_quantity_is_one(self) -> None:
        """quantity を渡さなければ 1 個 remove。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.REMOVE_ITEM,
            parameters={"item_spec_id": 7},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
        )
        assert len(result.item_spec_ids_to_remove) == 1


def _switch_obj() -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(1),
        name="switch",
        description="d",
        object_type=SpotObjectTypeEnum.OTHER,
        state={},
        interactions=(),
    )


class TestHasItemRequiredQuantity:
    """HAS_ITEM precondition の required_quantity。"""

    def _interaction(self, cond: InteractionCondition) -> InteractionDef:
        return InteractionDef(
            action_name="x",
            display_label="X",
            preconditions=(cond,),
            effects=(),
        )

    def test_default_required_quantity_is_one(self) -> None:
        """required_quantity 未指定なら従来通り「1 個以上」で OK。"""
        svc = SpotInteractionService()
        spec = ItemSpecId.create(7)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.HAS_ITEM,
            target_item_spec_id=spec,
        )
        ok, _ = svc.can_interact(
            self._interaction(cond), _switch_obj(),
            owned_item_spec_ids=frozenset({spec}),
            world_flags=frozenset(),
        )
        assert ok is True

    def test_required_quantity_n_passes_when_owned_n(self) -> None:
        """required_quantity=2 で 2 個保持していれば OK。"""
        svc = SpotInteractionService()
        spec = ItemSpecId.create(7)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.HAS_ITEM,
            target_item_spec_id=spec,
            required_quantity=2,
        )
        ok, _ = svc.can_interact(
            self._interaction(cond), _switch_obj(),
            owned_item_spec_ids=frozenset({spec}),
            world_flags=frozenset(),
            owned_item_spec_counts={spec: 2},
        )
        assert ok is True

    def test_required_quantity_n_fails_when_owned_less(self) -> None:
        """required_quantity=3 で 2 個しか持っていなければ拒否。"""
        svc = SpotInteractionService()
        spec = ItemSpecId.create(7)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.HAS_ITEM,
            target_item_spec_id=spec,
            required_quantity=3,
            failure_message="鉱石が 3 個必要です",
        )
        ok, msg = svc.can_interact(
            self._interaction(cond), _switch_obj(),
            owned_item_spec_ids=frozenset({spec}),
            world_flags=frozenset(),
            owned_item_spec_counts={spec: 2},
        )
        assert ok is False
        assert msg == "鉱石が 3 個必要です"

    def test_required_quantity_two_with_counts_none_raises(self) -> None:
        """counts=None かつ required_quantity>1 は silent wrong answer を避けるため早期 ValueError。"""
        import pytest

        svc = SpotInteractionService()
        spec = ItemSpecId.create(7)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.HAS_ITEM,
            target_item_spec_id=spec,
            required_quantity=2,
        )
        with pytest.raises(ValueError, match="owned_item_spec_counts is required"):
            svc.can_interact(
                self._interaction(cond), _switch_obj(),
                owned_item_spec_ids=frozenset({spec}),
                world_flags=frozenset(),
                # counts を渡さない
            )

    def test_required_quantity_one_with_counts_none_passes_via_frozenset_fallback(self) -> None:
        """required_quantity=1 (default) なら counts=None でも frozenset フォールバックで OK。"""
        svc = SpotInteractionService()
        spec = ItemSpecId.create(7)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.HAS_ITEM,
            target_item_spec_id=spec,
            # required_quantity は default の 1
        )
        ok, _ = svc.can_interact(
            self._interaction(cond), _switch_obj(),
            owned_item_spec_ids=frozenset({spec}),
            world_flags=frozenset(),
            # counts を渡さない
        )
        assert ok is True


class TestRequiredQuantityScenarioLoader:
    """scenario_loader 側の required_quantity バリデーション。"""

    def test_negative_required_quantity_rejected(self) -> None:
        """`required_quantity: 0` は ScenarioLoadError を投げる。"""
        import pytest

        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoader, ScenarioLoadError,
        )

        scenario = {
            "scenario_format_version": "1.0",
            "metadata": {
                "id": "x", "title": "x", "description": "x",
                "theme": "x", "difficulty": "easy", "estimated_ticks": 1, "author": "x", "tags": [],
            },
            "item_specs": [
                {"id": "ore", "name": "鉱石", "description": "d", "category": "MATERIAL"},
            ],
            "environment": {
                "weather": {"enabled": False, "initial": {"weather_type": "CLEAR", "intensity": 0.0},
                            "update_interval_ticks": 100, "announce_changes": False},
            },
            "spots": [{
                "id": "s", "name": "S", "description": "d", "category": "OTHER",
                "atmosphere": {"lighting": "DIM", "temperature": "NORMAL"},
                "interior": {"objects": [{
                    "id": "o", "name": "O", "description": "d", "object_type": "OTHER",
                    "state": {},
                    "interactions": [{
                        "action_name": "x", "display_label": "X",
                        "preconditions": [{
                            "condition_type": "HAS_ITEM",
                            "required_item": "ore",
                            "required_quantity": 0,  # 不正
                        }],
                        "effects": [],
                    }],
                }]},
            }],
            "connections": [],
            "players": [{"id": "p", "name": "P", "spawn_spot": "s", "initial_items": []}],
            "game_end_conditions": {"win": [], "lose": []},
        }
        with pytest.raises(ScenarioLoadError, match="required_quantity"):
            ScenarioLoader().load_from_dict(scenario)


class TestHasItemsRequiredQuantity:
    """HAS_ITEMS precondition の required_quantity (各 spec に同値適用)。"""

    def test_each_spec_must_meet_required_quantity(self) -> None:
        """required_quantity=2 で全 spec が 2 個以上なら OK。"""
        svc = SpotInteractionService()
        a = ItemSpecId.create(1)
        b = ItemSpecId.create(2)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.HAS_ITEMS,
            required_item_spec_ids=(a, b),
            required_quantity=2,
        )
        idef = InteractionDef(
            action_name="x", display_label="X",
            preconditions=(cond,), effects=(),
        )
        ok, _ = svc.can_interact(
            idef, _switch_obj(),
            owned_item_spec_ids=frozenset({a, b}),
            world_flags=frozenset(),
            owned_item_spec_counts={a: 2, b: 3},
        )
        assert ok is True

    def test_one_spec_below_required_fails(self) -> None:
        """1 種でも required_quantity に足りなければ拒否。"""
        svc = SpotInteractionService()
        a = ItemSpecId.create(1)
        b = ItemSpecId.create(2)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.HAS_ITEMS,
            required_item_spec_ids=(a, b),
            required_quantity=2,
        )
        idef = InteractionDef(
            action_name="x", display_label="X",
            preconditions=(cond,), effects=(),
        )
        ok, _ = svc.can_interact(
            idef, _switch_obj(),
            owned_item_spec_ids=frozenset({a, b}),
            world_flags=frozenset(),
            owned_item_spec_counts={a: 5, b: 1},
        )
        assert ok is False
