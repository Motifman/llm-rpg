"""Phase 4-A PR 2: item instance state を操作する effect / precondition のテスト。

新規追加:
- `CHANGE_ITEM_INSTANCE_STATE` effect — acting item instance の state を merge
- `RECORD_ITEM_INSTANCE_STATE_TICK` effect — current_tick.value を state[key] に書く
- `ITEM_INSTANCE_STATE` precondition — acting item instance の state を判定

acting_item_aggregate が渡されないとき silent failure を避けるため:
- effect 系は warning ログを出して no-op
- precondition は False を返して interaction を拒否
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


def _lantern_aggregate(initial_state: dict | None = None) -> ItemAggregate:
    spec = ItemSpec(
        item_spec_id=ItemSpecId(7),
        name="Lantern",
        item_type=ItemType.MATERIAL,
        rarity=Rarity.COMMON,
        description="A lantern.",
        max_stack_size=MaxStackSize(64),
    )
    return ItemAggregate.create(
        item_instance_id=ItemInstanceId(101),
        item_spec=spec,
        quantity=1,
        state=initial_state,
    )


class TestChangeItemInstanceStateEffect:
    """CHANGE_ITEM_INSTANCE_STATE effect の挙動。"""

    def test_merges_state_updates_into_acting_item(self) -> None:
        """state_updates が acting_item_aggregate にマージされる。"""
        svc = WorldGraphEffectService()
        agg = _lantern_aggregate(initial_state={"lit": False, "fuel": 5})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"lit": True}},
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
            acting_item_aggregate=agg,
        )
        # 部分マージ: lit のみ書き換え、fuel は残る
        assert agg.state == {"lit": True, "fuel": 5}
        assert result.item_instance_state_changed is True

    def test_no_op_and_warn_when_acting_item_is_none(self, caplog) -> None:
        """acting_item_aggregate を渡さない場合、警告ログを出して state を変えない。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE,
            parameters={"state_updates": {"lit": True}},
        )
        with caplog.at_level(logging.WARNING):
            result = svc.apply_effects(
                interior=_empty_interior(),
                acting_object=None,
                effects=[effect],
                world_flags=frozenset(),
                # acting_item_aggregate を渡さない
            )
        assert result.item_instance_state_changed is False
        assert any("acting_item_aggregate" in r.message for r in caplog.records)

    def test_no_op_when_state_updates_is_not_dict(self, caplog) -> None:
        """parameters.state_updates が dict 以外なら警告 + no-op。"""
        svc = WorldGraphEffectService()
        agg = _lantern_aggregate(initial_state={"lit": False})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE,
            parameters={"state_updates": "lit=true"},  # 不正
        )
        with caplog.at_level(logging.WARNING):
            result = svc.apply_effects(
                interior=_empty_interior(),
                acting_object=None,
                effects=[effect],
                world_flags=frozenset(),
                acting_item_aggregate=agg,
            )
        assert agg.state == {"lit": False}
        assert result.item_instance_state_changed is False


class TestRecordItemInstanceStateTickEffect:
    """RECORD_ITEM_INSTANCE_STATE_TICK effect の挙動。"""

    def test_writes_current_tick_into_state_key(self) -> None:
        """current_tick.value を state[state_key] に書き込む。"""
        svc = WorldGraphEffectService()
        agg = _lantern_aggregate(initial_state={"lit": True})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_ITEM_INSTANCE_STATE_TICK,
            parameters={"state_key": "lit_at_tick"},
        )
        result = svc.apply_effects(
            interior=_empty_interior(),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(42),
            acting_item_aggregate=agg,
        )
        assert agg.state == {"lit": True, "lit_at_tick": 42}
        assert result.item_instance_state_changed is True

    def test_no_op_when_current_tick_missing(self, caplog) -> None:
        """current_tick が None なら警告 + no-op (silent failure 回避)。"""
        svc = WorldGraphEffectService()
        agg = _lantern_aggregate()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_ITEM_INSTANCE_STATE_TICK,
            parameters={"state_key": "lit_at_tick"},
        )
        with caplog.at_level(logging.WARNING):
            svc.apply_effects(
                interior=_empty_interior(),
                acting_object=None,
                effects=[effect],
                world_flags=frozenset(),
                acting_item_aggregate=agg,
                # current_tick を渡さない
            )
        assert "lit_at_tick" not in agg.state

    def test_no_op_when_state_key_missing(self, caplog) -> None:
        """state_key が無ければ警告 + no-op。"""
        svc = WorldGraphEffectService()
        agg = _lantern_aggregate()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_ITEM_INSTANCE_STATE_TICK,
            parameters={},
        )
        with caplog.at_level(logging.WARNING):
            svc.apply_effects(
                interior=_empty_interior(),
                acting_object=None,
                effects=[effect],
                world_flags=frozenset(),
                current_tick=WorldTick(1),
                acting_item_aggregate=agg,
            )
        assert agg.state == {}

    def test_no_op_when_acting_item_missing(self, caplog) -> None:
        """acting_item_aggregate が None なら警告 + no-op。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_ITEM_INSTANCE_STATE_TICK,
            parameters={"state_key": "lit_at_tick"},
        )
        with caplog.at_level(logging.WARNING):
            result = svc.apply_effects(
                interior=_empty_interior(),
                acting_object=None,
                effects=[effect],
                world_flags=frozenset(),
                current_tick=WorldTick(1),
                # acting_item_aggregate を渡さない
            )
        assert result.item_instance_state_changed is False


class TestItemInstanceStatePrecondition:
    """ITEM_INSTANCE_STATE precondition の挙動。"""

    def _switch_obj(self) -> SpotObject:
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
            action_name="x",
            display_label="X",
            preconditions=(cond,),
            effects=(),
        )

    def test_passes_when_state_matches(self) -> None:
        """acting item の state が required_state と一致すれば成立。"""
        svc = SpotInteractionService()
        agg = _lantern_aggregate(initial_state={"lit": True, "fuel": 3})
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.ITEM_INSTANCE_STATE,
            required_state={"lit": True},
        )
        ok, _ = svc.can_interact(
            self._interaction_with(cond), self._switch_obj(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_item_aggregate=agg,
        )
        assert ok is True

    def test_fails_when_state_differs(self) -> None:
        """acting item の state が required_state と不一致なら拒否。"""
        svc = SpotInteractionService()
        agg = _lantern_aggregate(initial_state={"lit": False})
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.ITEM_INSTANCE_STATE,
            required_state={"lit": True},
            failure_message="ランタンに火を点けてから使う必要がある",
        )
        ok, msg = svc.can_interact(
            self._interaction_with(cond), self._switch_obj(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_item_aggregate=agg,
        )
        assert ok is False
        assert msg == "ランタンに火を点けてから使う必要がある"

    def test_fails_when_acting_item_is_none(self) -> None:
        """acting_item_aggregate を渡さない場合、precondition は失敗する (silent pass を避ける)。"""
        svc = SpotInteractionService()
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.ITEM_INSTANCE_STATE,
            required_state={"lit": True},
        )
        ok, msg = svc.can_interact(
            self._interaction_with(cond), self._switch_obj(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            # acting_item_aggregate を渡さない
        )
        assert ok is False
        assert "acting item" in (msg or "") or "use_item" in (msg or "")

    def test_required_state_with_multiple_keys_all_match(self) -> None:
        """required_state が複数キーを持つ場合、全て一致で成立。1 つでも不一致なら拒否。"""
        svc = SpotInteractionService()
        agg = _lantern_aggregate(initial_state={"lit": True, "fuel": 3})
        cond_pass = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.ITEM_INSTANCE_STATE,
            required_state={"lit": True, "fuel": 3},
        )
        cond_fail = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.ITEM_INSTANCE_STATE,
            required_state={"lit": True, "fuel": 5},
        )
        for cond, expected in ((cond_pass, True), (cond_fail, False)):
            ok, _ = svc.can_interact(
                self._interaction_with(cond), self._switch_obj(),
                owned_item_spec_ids=frozenset(),
                world_flags=frozenset(),
                acting_item_aggregate=agg,
            )
            assert ok is expected
