import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GameEndConditionValidationException,
)
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import GameEndConditionEvaluator
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import GameEndCondition
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import (
    GameResultEnum,
)

#: 「成立したか」だけを見る試験で使う既定。勝敗はシナリオがどちらのリストに
#: 書いたかで決まるので、成立の有無しか見ないなら片側に固定して構わない。
#:
#: 返り値が WIN であることまで見る試験は、**呼び出し側で WIN を渡す**。
#: ここを共有の既定にすると、勝敗が呼び出し側で決まるという要点が消える。
_SIDE = GameResultEnum.LOSE



def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def test_flag_set_win() -> None:
    ev = GameEndConditionEvaluator()
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.place_entity(EntityId.create(1), SpotId.create(1))
    cond = GameEndCondition(
        condition_type=GameEndConditionTypeEnum.FLAG_SET,
        target_flag="escaped",
    )
    r = ev.evaluate(g, cond, frozenset({"escaped"}), [PlayerId(1)],
        result_on_match=GameResultEnum.WIN,
    )
    assert r.is_ended and r.result == GameResultEnum.WIN


def test_all_at_spot_win() -> None:
    ev = GameEndConditionEvaluator()
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.place_entity(EntityId.create(1), SpotId.create(2))
    g.place_entity(EntityId.create(2), SpotId.create(2))
    cond = GameEndCondition(
        condition_type=GameEndConditionTypeEnum.ALL_AT_SPOT,
        target_spot_id=SpotId.create(2),
    )
    r = ev.evaluate(g, cond, frozenset(), [PlayerId(1), PlayerId(2)],
        result_on_match=GameResultEnum.WIN,
    )
    assert r.is_ended and r.result == GameResultEnum.WIN


def test_tick_limit_lose() -> None:
    ev = GameEndConditionEvaluator()
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.place_entity(EntityId.create(1), SpotId.create(1))
    cond = GameEndCondition(
        condition_type=GameEndConditionTypeEnum.TICK_LIMIT,
        tick_limit=10,
    )
    r = ev.evaluate(g, cond, frozenset(), [PlayerId(1)], current_tick=WorldTick(10),
        result_on_match=_SIDE,
    )
    assert r.is_ended and r.result == GameResultEnum.LOSE


def test_invalid_flag_set_condition_raises_domain_exception_on_construction() -> None:
    """FLAG_SET に target_flag が無い条件は、評価前の構築時点で拒否される。"""
    with pytest.raises(GameEndConditionValidationException, match="target_flag"):
        GameEndCondition(condition_type=GameEndConditionTypeEnum.FLAG_SET)


@pytest.mark.parametrize(
    ("condition_type", "kwargs", "message"),
    [
        (GameEndConditionTypeEnum.TICK_LIMIT, {}, "tick_limit"),
        (GameEndConditionTypeEnum.ALL_AT_SPOT, {}, "target_spot_id"),
        (GameEndConditionTypeEnum.ANY_AT_SPOT, {}, "target_spot_id"),
    ],
)
def test_required_game_end_condition_fields_are_rejected_on_construction(
    condition_type: GameEndConditionTypeEnum,
    kwargs: dict,
    message: str,
) -> None:
    """条件型ごとの必須フィールド欠落は、値オブジェクトの構築時点で拒否される。"""
    with pytest.raises(GameEndConditionValidationException, match=message):
        GameEndCondition(condition_type=condition_type, **kwargs)
