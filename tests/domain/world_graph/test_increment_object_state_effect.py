"""INCREMENT_OBJECT_STATE effect 検証 (#3 採取の枯渇)。

state[key] += delta (default 1) で accumulator semantics を実現する effect。
CHANGE_OBJECT_STATE は「上書き」だけなので、採取回数のような累積カウントは
本 effect が必要。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


OBJ_ID = SpotObjectId.create(1)


def _make_interior_with_state(state: dict) -> SpotInterior:
    obj = SpotObject(
        object_id=OBJ_ID, name="test_obj", description="t",
        object_type=ObjectTypeEnum.RESOURCE, state=state, interactions=(),
    )
    return SpotInterior(sub_locations=(), objects=(obj,), ground_items=(), discoverable_items=())


def _apply_effect(interior: SpotInterior, params: dict) -> SpotInterior:
    svc = WorldGraphEffectService()
    effect = InteractionEffect(
        effect_type=InteractionEffectTypeEnum.INCREMENT_OBJECT_STATE,
        parameters={**params, "object_id": OBJ_ID.value},
    )
    result = svc.apply_effects(
        effects=(effect,),
        interior=interior,
        acting_object=None,
        world_flags=frozenset(),
    )
    return result.new_interior


class TestIncrementBasic:
    def test_default_delta_1_で_state_が_1_増える(self) -> None:
        interior = _make_interior_with_state({"harvest_count": 5})
        new_interior = _apply_effect(interior, {"state_key": "harvest_count"})
        new_obj = new_interior.get_object(OBJ_ID)
        assert new_obj.state["harvest_count"] == 6

    def test_明示_delta_で_指定量_増える(self) -> None:
        interior = _make_interior_with_state({"harvest_count": 5})
        new_interior = _apply_effect(
            interior, {"state_key": "harvest_count", "delta": 3},
        )
        new_obj = new_interior.get_object(OBJ_ID)
        assert new_obj.state["harvest_count"] == 8

    def test_負の_delta_で_減らすことも可能(self) -> None:
        """例: 食料消費で stock を 1 減らす等、汎用 accumulator。"""
        interior = _make_interior_with_state({"stock": 10})
        new_interior = _apply_effect(
            interior, {"state_key": "stock", "delta": -2},
        )
        new_obj = new_interior.get_object(OBJ_ID)
        assert new_obj.state["stock"] == 8

    def test_state_key_不在は_0_から_カウント開始(self) -> None:
        interior = _make_interior_with_state({})
        new_interior = _apply_effect(interior, {"state_key": "harvest_count"})
        new_obj = new_interior.get_object(OBJ_ID)
        assert new_obj.state["harvest_count"] == 1

    def test_非整数値は_0_扱いで_再初期化(self) -> None:
        """文字列等が入っていたら 0 扱いで上書きする (silent fallback)。"""
        interior = _make_interior_with_state({"harvest_count": "invalid"})
        new_interior = _apply_effect(interior, {"state_key": "harvest_count"})
        new_obj = new_interior.get_object(OBJ_ID)
        assert new_obj.state["harvest_count"] == 1
