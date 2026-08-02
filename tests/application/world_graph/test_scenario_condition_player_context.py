"""ScenarioConditionEvaluator が世界条件と対象者条件を同じ語彙で評価する契約。"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


_TARGET_SPOT = SpotId.create(10)
_OTHER_SPOT = SpotId.create(20)


def _evaluator() -> ScenarioConditionEvaluator:
    return ScenarioConditionEvaluator(
        world_flag_state=MutableWorldFlagState(),
        spot_interior_repository=MagicMock(),
        player_status_repository=MagicMock(),
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
    )


def _graph() -> SpotGraphAggregate:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for spot_id, name in ((_TARGET_SPOT, "対象地"), (_OTHER_SPOT, "別の場所")):
        graph.add_spot(
            SpotNode(
                spot_id=spot_id,
                name=name,
                description=name,
                category=SpotCategoryEnum.OTHER,
                parent_id=None,
            )
        )
    graph.place_entity(EntityId.create(1), _TARGET_SPOT)
    graph.place_entity(EntityId.create(2), _OTHER_SPOT)
    return graph


def _player_at_target_condition() -> ScenarioEventCondition:
    return ScenarioEventCondition(
        condition_type="PLAYER_AT_SPOT",
        spot_id=_TARGET_SPOT.value,
    )


class TestWorldScopedEvaluation:
    """対象者を指定しない既存入口は世界全体の条件として評価する。"""

    def test_player_at_spot_matches_when_any_entity_is_there(self) -> None:
        """対象者未指定なら、従来どおり誰か一人が対象地にいれば成立する。"""
        assert _evaluator().evaluate(
            _player_at_target_condition(),
            WorldTick(0),
            _graph(),
        ) is True


class TestPlayerScopedEvaluation:
    """対象者専用入口は他者の状態を対象者へ取り違えない。"""

    def test_player_at_spot_matches_the_requested_player(self) -> None:
        """指定した本人が対象地にいれば対象者条件は成立する。"""
        assert _evaluator().evaluate_for_player(
            _player_at_target_condition(),
            WorldTick(0),
            _graph(),
            target_player_id=PlayerId(1),
        ) is True

    def test_single_condition_checks_the_requested_player(self) -> None:
        """単数入口でも、別人が対象地にいるだけなら本人の条件は成立しない。"""
        assert _evaluator().evaluate_for_player(
            _player_at_target_condition(),
            WorldTick(0),
            _graph(),
            target_player_id=PlayerId(2),
        ) is False

    def test_single_condition_rejects_missing_target_player(self) -> None:
        """単数入口へ PlayerId を渡し忘れると世界条件へ縮退せず失敗する。"""
        with pytest.raises(TypeError, match="target_player_id"):
            _evaluator().evaluate_for_player(
                _player_at_target_condition(),
                WorldTick(0),
                _graph(),
                target_player_id=None,  # type: ignore[arg-type]
            )

    def test_player_at_spot_checks_the_requested_player(self) -> None:
        """別人が対象地にいても、指定した本人が別の場所なら成立しない。"""
        assert _evaluator().evaluate_all_for_player(
            (_player_at_target_condition(),),
            WorldTick(0),
            _graph(),
            target_player_id=PlayerId(2),
        ) is False

    def test_missing_target_player_is_rejected(self) -> None:
        """対象者専用入口へ PlayerId を渡し忘れた場合は世界条件へ縮退せず失敗する。"""
        with pytest.raises(TypeError, match="target_player_id"):
            _evaluator().evaluate_all_for_player(
                (_player_at_target_condition(),),
                WorldTick(0),
                _graph(),
                target_player_id=None,  # type: ignore[arg-type]
            )
