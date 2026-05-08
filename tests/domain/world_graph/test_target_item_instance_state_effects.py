"""Phase 4-B: cross-instance interaction で「使われる側 (target)」の
item instance を操作する effect / precondition のテスト。

PR 110 で acting (使う側) 用の primitive が揃った。本 PR はそれと並列の
「target (使われる側)」用 primitive を追加する。これで「修理キット (acting) を
錆びた剣 (target) に使う」のような cross-instance interaction が宣言的に
書けるようになる。

新規追加:
- `CHANGE_TARGET_ITEM_INSTANCE_STATE` effect
- `RECORD_TARGET_ITEM_INSTANCE_STATE_TICK` effect
- `TARGET_ITEM_INSTANCE_STATE` precondition

各 effect / precondition は target_item_aggregate が渡されなかった場合に
silent failure を避ける（acting 側と同じガード方針）。
"""

from __future__ import annotations

import logging

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
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


def _item_aggregate(
    instance_id: int = 100, spec_id: int = 7,
    initial_state: dict | None = None,
) -> ItemAggregate:
    spec = ItemSpec(
        item_spec_id=ItemSpecId(spec_id),
        name=f"item-{spec_id}",
        item_type=ItemType.MATERIAL,
        rarity=Rarity.COMMON,
        description="d",
        max_stack_size=MaxStackSize(64),
    )
    return ItemAggregate.create(
        item_instance_id=ItemInstanceId(instance_id),
        item_spec=spec,
        quantity=1,
        state=initial_state,
    )


class TestChangeTargetItemInstanceStateEffect:
    """CHANGE_TARGET_ITEM_INSTANCE_STATE の挙動。"""

    def test_merges_into_target_not_acting(self) -> None:
        """target_item_aggregate に部分マージし、acting 側は不変。"""
        svc = WorldGraphEffectService()
        acting = _item_aggregate(instance_id=1, spec_id=10, initial_state={"role": "tool"})
        target = _item_aggregate(instance_id=2, spec_id=20, initial_state={"rust": "high"})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_TARGET_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"rust": "low"}},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
            acting_item_aggregate=acting,
            target_item_aggregate=target,
        )
        assert target.state == {"rust": "low"}
        # acting は触られない
        assert acting.state == {"role": "tool"}
        assert result.target_item_instance_state_changed is True
        assert result.item_instance_state_changed is False

    def test_no_op_and_warn_when_target_is_none(self, caplog) -> None:
        """target_item_aggregate を渡さない場合は警告 + no-op。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_TARGET_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"rust": "low"}},
        )
        with caplog.at_level(logging.WARNING):
            result = svc.apply_effects(
                interior=_empty_interior(), acting_object=None,
                effects=[effect], world_flags=frozenset(),
                # target_item_aggregate を渡さない
            )
        assert result.target_item_instance_state_changed is False
        assert any("target_item_aggregate" in r.message for r in caplog.records)

    def test_no_op_when_state_updates_not_dict(self, caplog) -> None:
        """state_updates が dict 以外なら警告 + no-op。"""
        svc = WorldGraphEffectService()
        target = _item_aggregate(initial_state={"rust": "high"})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_TARGET_ITEM_INSTANCE_STATE,
            parameters={"state_updates": "rust=low"},
        )
        with caplog.at_level(logging.WARNING):
            svc.apply_effects(
                interior=_empty_interior(), acting_object=None,
                effects=[effect], world_flags=frozenset(),
                target_item_aggregate=target,
            )
        assert target.state == {"rust": "high"}


class TestRecordTargetItemInstanceStateTickEffect:
    """RECORD_TARGET_ITEM_INSTANCE_STATE_TICK の挙動。"""

    def test_writes_current_tick_into_target_state(self) -> None:
        """current_tick.value が target.state[state_key] に書き込まれる。"""
        svc = WorldGraphEffectService()
        target = _item_aggregate(initial_state={"rust": "low"})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK,
            parameters={"state_key": "last_repaired_tick"},
        )
        svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
            current_tick=WorldTick(99),
            target_item_aggregate=target,
        )
        assert target.state == {"rust": "low", "last_repaired_tick": 99}

    def test_no_op_when_target_missing(self, caplog) -> None:
        """target_item_aggregate が None なら警告 + no-op。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK,
            parameters={"state_key": "x"},
        )
        with caplog.at_level(logging.WARNING):
            result = svc.apply_effects(
                interior=_empty_interior(), acting_object=None,
                effects=[effect], world_flags=frozenset(),
                current_tick=WorldTick(1),
            )
        assert result.target_item_instance_state_changed is False

    def test_no_op_when_current_tick_missing(self, caplog) -> None:
        """current_tick が None なら警告 + no-op。"""
        svc = WorldGraphEffectService()
        target = _item_aggregate()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK,
            parameters={"state_key": "x"},
        )
        with caplog.at_level(logging.WARNING):
            svc.apply_effects(
                interior=_empty_interior(), acting_object=None,
                effects=[effect], world_flags=frozenset(),
                target_item_aggregate=target,
            )
        assert target.state == {}


class TestTargetItemInstanceStatePrecondition:
    """TARGET_ITEM_INSTANCE_STATE の挙動。"""

    def _switch(self) -> SpotObject:
        return SpotObject(
            object_id=SpotObjectId.create(1),
            name="switch",
            description="d",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(),
        )

    def _interaction_with(self, cond: InteractionCondition) -> InteractionDef:
        return InteractionDef(
            action_name="x", display_label="X",
            preconditions=(cond,), effects=(),
        )

    def test_passes_when_target_state_matches(self) -> None:
        """target_item_aggregate.state が required_state と一致すれば成立。"""
        svc = SpotInteractionService()
        target = _item_aggregate(initial_state={"rust": "high"})
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_ITEM_INSTANCE_STATE,
            required_state={"rust": "high"},
        )
        ok, _ = svc.can_interact(
            self._interaction_with(cond), self._switch(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            target_item_aggregate=target,
        )
        assert ok is True

    def test_fails_when_target_state_differs(self) -> None:
        """target.state が required_state と不一致なら拒否。"""
        svc = SpotInteractionService()
        target = _item_aggregate(initial_state={"rust": "low"})
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_ITEM_INSTANCE_STATE,
            required_state={"rust": "high"},
            failure_message="この剣は錆びていない",
        )
        ok, msg = svc.can_interact(
            self._interaction_with(cond), self._switch(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            target_item_aggregate=target,
        )
        assert ok is False
        assert msg == "この剣は錆びていない"

    def test_fails_when_target_is_none(self) -> None:
        """target_item_aggregate を渡さない場合、precondition は失敗（silent pass を避ける）。"""
        svc = SpotInteractionService()
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_ITEM_INSTANCE_STATE,
            required_state={"rust": "high"},
        )
        ok, _ = svc.can_interact(
            self._interaction_with(cond), self._switch(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            # target_item_aggregate を渡さない
        )
        assert ok is False

    def test_acting_and_target_evaluated_independently(self) -> None:
        """acting / target を両方使う interaction で precondition が独立に判定される。"""
        svc = SpotInteractionService()
        repair_kit = _item_aggregate(instance_id=1, initial_state={"used": False})
        rusted_sword = _item_aggregate(instance_id=2, initial_state={"rust": "high"})
        idef = InteractionDef(
            action_name="repair",
            display_label="修理する",
            preconditions=(
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.ITEM_INSTANCE_STATE,
                    required_state={"used": False},
                ),
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.TARGET_ITEM_INSTANCE_STATE,
                    required_state={"rust": "high"},
                ),
            ),
            effects=(),
        )
        # 両方一致
        ok, _ = svc.can_interact(
            idef, self._switch(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_item_aggregate=repair_kit,
            target_item_aggregate=rusted_sword,
        )
        assert ok is True

        # target だけ条件外
        clean_sword = _item_aggregate(instance_id=3, initial_state={"rust": "low"})
        ok, _ = svc.can_interact(
            idef, self._switch(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_item_aggregate=repair_kit,
            target_item_aggregate=clean_sword,
        )
        assert ok is False


class TestSameInstanceGuard:
    """同一 instance を acting / target 両方に渡す wiring バグを早期に弾く。"""

    def test_apply_effects_rejects_same_instance_for_acting_and_target(self) -> None:
        """同じ aggregate を両側に渡すと ValueError で即座に拒否される。"""
        svc = WorldGraphEffectService()
        agg = _item_aggregate(initial_state={"x": 1})
        with pytest.raises(
            ValueError, match="must be distinct instances"
        ):
            svc.apply_effects(
                interior=_empty_interior(), acting_object=None,
                effects=[],
                world_flags=frozenset(),
                acting_item_aggregate=agg,
                target_item_aggregate=agg,  # 同じ参照
            )

    def test_can_interact_rejects_same_instance_for_acting_and_target(self) -> None:
        """precondition 段階でも同じく ValueError で拒否。"""
        svc = SpotInteractionService()
        agg = _item_aggregate(initial_state={"x": 1})
        spot_object = SpotObject(
            object_id=SpotObjectId.create(1),
            name="o", description="d",
            object_type=SpotObjectTypeEnum.OTHER,
            state={}, interactions=(),
        )
        idef = InteractionDef(
            action_name="x", display_label="X",
            preconditions=(), effects=(),
        )
        with pytest.raises(ValueError, match="must be distinct instances"):
            svc.can_interact(
                idef, spot_object,
                owned_item_spec_ids=frozenset(),
                world_flags=frozenset(),
                acting_item_aggregate=agg,
                target_item_aggregate=agg,
            )


class TestCombinedActingAndTargetEffects:
    """acting / target 両方を変更する interaction の積分挙動。"""

    def test_both_aggregates_can_be_modified_in_one_apply(self) -> None:
        """1 つの interaction で acting と target 両方の state を変えられる。

        例: 修理キットを使うと acting (キット) は used=true、target (剣) は rust=low。
        両方の state_changed フラグが返る。
        """
        svc = WorldGraphEffectService()
        kit = _item_aggregate(instance_id=1, initial_state={"used": False})
        sword = _item_aggregate(instance_id=2, initial_state={"rust": "high"})
        effects = [
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE,
                parameters={"state_updates": {"used": True}},
            ),
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.CHANGE_TARGET_ITEM_INSTANCE_STATE,
                parameters={"state_updates": {"rust": "low"}},
            ),
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK,
                parameters={"state_key": "last_repaired_tick"},
            ),
        ]
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=effects, world_flags=frozenset(),
            current_tick=WorldTick(7),
            acting_item_aggregate=kit,
            target_item_aggregate=sword,
        )
        assert kit.state == {"used": True}
        assert sword.state == {"rust": "low", "last_repaired_tick": 7}
        assert result.item_instance_state_changed is True
        assert result.target_item_instance_state_changed is True
