"""備蓄プール (stock pool) の condition/effect 統合テスト。

- OBJECT_STOCK_AT_LEAST precondition: 現在備蓄 (lazy 再生) が required_quantity
  以上あるときだけ interaction を許可する。
- CONSUME_OBJECT_STOCK effect: 現在備蓄を lazy 算出してから amount 消費し、
  (stock, stock_tick) を書き戻す。
毎 tick 更新せず、アクセス時 (precondition 評価 / effect 適用) に現在 tick から
再生を計算する lazy モデルの動作を固定する。
"""

from __future__ import annotations

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import (
    InteractionDef,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

OBJ_ID = SpotObjectId.create(1)


def _pool_object(**state) -> SpotObject:
    base = {
        "stock": 6, "stock_capacity": 6,
        "stock_tick": 0, "stock_refill_interval": 8,
    }
    base.update(state)
    return SpotObject(
        object_id=OBJ_ID, name="貝の岩棚", description="t",
        object_type=ObjectTypeEnum.RESOURCE, state=base, interactions=(),
    )


def _interior(obj: SpotObject) -> SpotInterior:
    return SpotInterior(
        sub_locations=(), objects=(obj,), ground_items=(), discoverable_items=()
    )


class TestConsumeObjectStockEffect:
    """CONSUME_OBJECT_STOCK が現在備蓄を lazy 算出して amount 消費する。"""

    def _consume(self, obj: SpotObject, amount: int, now: int) -> SpotObject:
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CONSUME_OBJECT_STOCK,
            parameters={"object_id": OBJ_ID.value, "amount": amount},
        )
        result = svc.apply_effects(
            effects=(effect,),
            interior=_interior(obj),
            acting_object=None,
            world_flags=frozenset(),
            current_tick=WorldTick(now),
        )
        return result.new_interior.get_object(OBJ_ID)

    def test_consume_decrements_stock(self) -> None:
        """再生ゼロ (now==stock_tick) なら stock がそのまま amount 減る。"""
        obj = self._consume(_pool_object(stock=6, stock_tick=0), amount=3, now=0)
        assert obj.state["stock"] == 3

    def test_consume_credits_regen_first(self) -> None:
        """消費前に経過 tick 分の再生を加算する (0 → 24tick/interval8 → 3 → -3 → 0)。"""
        obj = self._consume(
            _pool_object(stock=0, stock_capacity=6, stock_tick=0, stock_refill_interval=8),
            amount=3, now=24,
        )
        assert obj.state["stock"] == 0
        assert obj.state["stock_tick"] == 24  # 満杯未満だが 3*8=24 消費、端数0

    def test_consume_writes_canonical_tick(self) -> None:
        """満杯からの消費では stock_tick が now に揃う (端数を溜めない)。"""
        obj = self._consume(
            _pool_object(stock=6, stock_capacity=6, stock_tick=0, stock_refill_interval=8),
            amount=2, now=50,
        )
        assert obj.state["stock"] == 4
        assert obj.state["stock_tick"] == 50


class TestObjectStockAtLeastCondition:
    """OBJECT_STOCK_AT_LEAST が現在備蓄で interaction 可否を判定する。"""

    def _can(self, obj: SpotObject, required: int, now: int):
        svc = SpotInteractionService(effect_service=WorldGraphEffectService())
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.OBJECT_STOCK_AT_LEAST,
            target_object_id=OBJ_ID,
            required_quantity=required,
            failure_message="採り尽くした。時間が経てば戻る",
        )
        idef = InteractionDef(
            action_name="gather", display_label="採る",
            preconditions=(cond,), effects=(),
        )
        return svc.can_interact(
            idef, obj, frozenset(), frozenset(),
            current_tick=WorldTick(now),
        )

    def test_enough_stock_allows(self) -> None:
        """備蓄 >= required なら許可。"""
        ok, msg = self._can(_pool_object(stock=6, stock_tick=0), required=3, now=0)
        assert ok is True

    def test_insufficient_stock_blocks_with_message(self) -> None:
        """備蓄 < required なら失敗メッセージ付きで拒否。"""
        ok, msg = self._can(_pool_object(stock=2, stock_tick=0), required=3, now=0)
        assert ok is False
        assert "採り尽くした" in msg

    def test_regen_restores_availability(self) -> None:
        """枯渇後も経過 tick の再生で再び採れるようになる (0 → 24tick → 3)。"""
        obj = _pool_object(stock=0, stock_capacity=6, stock_tick=0, stock_refill_interval=8)
        ok_before, _ = self._can(obj, required=3, now=0)
        ok_after, _ = self._can(obj, required=3, now=24)
        assert ok_before is False
        assert ok_after is True
