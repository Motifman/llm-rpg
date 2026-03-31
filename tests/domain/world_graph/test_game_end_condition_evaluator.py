from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import GameEndConditionEvaluator
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import GameEndCondition
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


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
    r = ev.evaluate(g, cond, frozenset({"escaped"}), [PlayerId(1)])
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
    r = ev.evaluate(g, cond, frozenset(), [PlayerId(1), PlayerId(2)])
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
    r = ev.evaluate(g, cond, frozenset(), [PlayerId(1)], current_tick=WorldTick(10))
    assert r.is_ended and r.result == GameResultEnum.LOSE
