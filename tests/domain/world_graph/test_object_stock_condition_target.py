"""備蓄条件は宣言した対象を読み、操作元の在庫で許可・拒否を取り違えない。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import InteractionNotAllowedException
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import SpotInteractionService
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _pool(
    object_id: SpotObjectId,
    stock: int,
    interactions: tuple[InteractionDef, ...] = (),
) -> SpotObject:
    return SpotObject(
        object_id=object_id,
        name=f"資源{object_id.value}",
        description="",
        object_type=SpotObjectTypeEnum.OTHER,
        state={
            "stock": stock,
            "stock_capacity": 6,
            "stock_tick": 0,
            "stock_refill_interval": 8,
        },
        interactions=interactions,
    )


@pytest.mark.parametrize(
    ("entrypoint", "target_kind", "actor_stock", "target_stock", "remaining_stock"),
    [
        ("object", "other", 0, 3, 1),
        ("object", "other", 3, 0, None),
        ("declared", "other", 0, 3, 1),
        ("object", "missing", 3, 3, None),
        ("object", "self", 3, 0, 1),
        ("object", "implicit", 3, 0, 1),
    ],
    ids=[
        "named-target-has-stock",
        "named-target-is-empty",
        "declared-action-has-no-acting-object",
        "missing-target-does-not-use-actor",
        "explicit-self-target",
        "implicit-acting-target",
    ],
)
def test_stock_condition_and_consumption_use_the_declared_target(
    entrypoint: str,
    target_kind: str,
    actor_stock: int,
    target_stock: int,
    remaining_stock: int | None,
) -> None:
    """指定先に2個以上あればその物体だけを消費し、不足・不在なら状態を変えず拒否する。

    操作元のない宣言済み操作でも明示対象を使う。対象省略と自分自身の明示は、
    従来どおり操作元を使う。現在手番を0に固定し、再生で対照が逆転しないようにする。
    """
    actor_id, resource_id = SpotObjectId.create(1), SpotObjectId.create(2)
    target_id = {
        "other": resource_id,
        "missing": SpotObjectId.create(3),
        "self": actor_id,
        "implicit": None,
    }[target_kind]
    condition = InteractionCondition(
        condition_type=InteractionConditionTypeEnum.OBJECT_STOCK_AT_LEAST,
        target_object_id=target_id,
        required_quantity=2,
        failure_message="指定した資源の備蓄が足りない",
    )
    parameters = {"amount": 2}
    if target_id is not None:
        parameters["object_id"] = target_id.value
    action = InteractionDef(
        action_name="draw", display_label="資源を取り出す",
        preconditions=(condition,),
        effects=(InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CONSUME_OBJECT_STOCK,
            parameters=parameters,
        ),),
    )
    interior = SpotInterior(
        (), (_pool(actor_id, actor_stock, (action,)), _pool(resource_id, target_stock)), (), (),
    )
    before = {obj.object_id: dict(obj.state) for obj in interior.objects}
    service = SpotInteractionService()

    def execute():
        if entrypoint == "declared":
            return service.execute_declared_interaction(
                interior, action, frozenset(), frozenset(), current_tick=WorldTick(0),
            )
        return service.execute_interaction(
            interior, actor_id, "draw", frozenset(), frozenset(), current_tick=WorldTick(0),
        )

    if remaining_stock is None:
        with pytest.raises(InteractionNotAllowedException, match="指定した資源") as exc:
            execute()
        assert exc.value.failed_condition is condition
        assert {obj.object_id: obj.state for obj in interior.objects} == before
    else:
        result = execute()
        expected = {object_id: dict(state) for object_id, state in before.items()}
        expected[target_id or actor_id]["stock"] = remaining_stock
        assert {obj.object_id: obj.state for obj in result.new_interior.objects} == expected
        assert {obj.object_id: obj.state for obj in interior.objects} == before
