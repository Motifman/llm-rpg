"""RECORD_OBJECT_STATE_TICK エフェクトのユニットテスト。

#10 経時劣化 / #12 資源回復 で reactive binding の
OBJECT_STATE_TICK_AT_LEAST predicate が読む「最後にイベントが
起きた tick」を target object の state に書き込む effect の挙動を
検証する。
"""

from __future__ import annotations

import logging

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _bush(initial_state: dict) -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(7),
        name="berry_bush",
        description="d",
        object_type=SpotObjectTypeEnum.OTHER,
        state=dict(initial_state),
        interactions=(),
    )


def _interior_with(obj: SpotObject) -> SpotInterior:
    return SpotInterior((), (obj,), (), ())


class TestRecordObjectStateTickEffect:
    """RECORD_OBJECT_STATE_TICK の挙動。"""

    def test_writes_current_tick_into_state_key_on_acting_object(self) -> None:
        """acting_object の state[state_key] に current_tick.value が書き込まれる。"""
        svc = WorldGraphEffectService()
        bush = _bush({"available": True})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK,
            parameters={"state_key": "last_harvest_tick"},
        )
        result = svc.apply_effects(
            interior=_interior_with(bush),
            acting_object=bush,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(42),
        )
        new_obj = result.new_interior.objects[0]
        assert new_obj.state["last_harvest_tick"] == 42
        # 他のキーは保持
        assert new_obj.state["available"] is True

    def test_resolves_explicit_object_id_param(self) -> None:
        """object_id パラメータが渡されればそちらを優先する。"""
        svc = WorldGraphEffectService()
        bush = _bush({})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK,
            parameters={"object_id": 7, "state_key": "k"},
        )
        # acting_object=None でも object_id 解決で interior 内のオブジェクトを探す
        result = svc.apply_effects(
            interior=_interior_with(bush),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
            current_tick=WorldTick(5),
        )
        assert result.new_interior.objects[0].state["k"] == 5

    def test_no_op_when_current_tick_missing(self, caplog) -> None:
        """current_tick が None なら警告を出して書き込みをスキップする。"""
        svc = WorldGraphEffectService()
        bush = _bush({"available": True})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK,
            parameters={"state_key": "last_harvest_tick"},
        )
        with caplog.at_level(logging.WARNING):
            result = svc.apply_effects(
                interior=_interior_with(bush),
                acting_object=bush,
                effects=[effect],
                world_flags=frozenset(),
                # current_tick を渡さない
            )
        assert "last_harvest_tick" not in result.new_interior.objects[0].state
        assert any("current_tick" in r.message for r in caplog.records)

    def test_no_op_when_state_key_missing(self, caplog) -> None:
        """state_key が無ければ警告を出してスキップ。"""
        svc = WorldGraphEffectService()
        bush = _bush({"available": True})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK,
            parameters={},
        )
        with caplog.at_level(logging.WARNING):
            result = svc.apply_effects(
                interior=_interior_with(bush),
                acting_object=bush,
                effects=[effect],
                world_flags=frozenset(),
                current_tick=WorldTick(1),
            )
        # state は変わらない
        assert result.new_interior.objects[0].state == {"available": True}
        assert any("state_key" in r.message for r in caplog.records)
