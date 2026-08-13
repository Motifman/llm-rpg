"""二つの陣営の生存数を比較して終了条件を判定できることを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
    GameEndConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GameEndConditionValidationException,
)
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import (
    GameEndCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


_CREW = tuple(PlayerId(value) for value in (1, 2, 3))
_KEEPERS = tuple(PlayerId(value) for value in (4, 5))
_ALL = (*_CREW, *_KEEPERS)
_STATES = {
    **{int(player_id): {"role": "crew"} for player_id in _CREW},
    **{int(player_id): {"role": "keeper"} for player_id in _KEEPERS},
}


def _graph() -> SpotGraphAggregate:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(
        SpotNode(
            spot_id=SpotId.create(1),
            name="集会室",
            description="試験用の部屋。",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
        )
    )
    for player_id in _ALL:
        graph.place_entity(EntityId.create(int(player_id)), SpotId.create(1))
    return graph


def _condition() -> GameEndCondition:
    return GameEndCondition(
        condition_type=(
            GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE
        ),
        required_state={"role": "crew"},
        comparison_state={"role": "keeper"},
    )


def _outcomes(
    *,
    dead: tuple[PlayerId, ...] = (),
    ejected: tuple[PlayerId, ...] = (),
) -> dict[int, PlayerOutcomeEnum]:
    outcomes = {int(player_id): PlayerOutcomeEnum.UNRESOLVED for player_id in _ALL}
    for player_id in dead:
        outcomes[int(player_id)] = PlayerOutcomeEnum.DEAD
    for player_id in ejected:
        outcomes[int(player_id)] = PlayerOutcomeEnum.EJECTED
    return outcomes


def _evaluate(outcomes: dict[int, PlayerOutcomeEnum]):
    return GameEndConditionEvaluator().evaluate(
        _graph(),
        _condition(),
        frozenset(),
        _ALL,
        player_states=_STATES,
        player_outcomes=outcomes,
        result_on_match=GameResultEnum.LOSE,
    )


class TestSurvivingPlayerGroupComparison:
    """左の陣営が右の陣営以下になった境界だけで成立する。"""

    def test_three_crew_against_two_keepers_does_not_end(self) -> None:
        """crew 3 人、keeper 2 人なら人数差が残っているので成立しない。"""
        assert _evaluate(_outcomes()).is_ended is False

    def test_two_crew_against_two_keepers_ends(self) -> None:
        """crew 2 人、keeper 2 人なら同数になったため成立する。"""
        result = _evaluate(_outcomes(dead=(_CREW[0],)))

        assert result.is_ended is True
        assert result.result is GameResultEnum.LOSE

    def test_two_crew_against_one_keeper_does_not_end(self) -> None:
        """keeper が 1 人退場済みなら crew 2 人で敗北にはならない。

        固定閾値を 2 にする方式との違いが現れる境界である。
        """
        result = _evaluate(
            _outcomes(dead=(_CREW[0],), ejected=(_KEEPERS[0],))
        )

        assert result.is_ended is False

    def test_dead_players_who_continue_as_ghosts_are_not_survivors(self) -> None:
        """DEAD の幽霊は作業を続けられても生存人数には含めない。"""
        result = _evaluate(_outcomes(dead=(_CREW[0],)))

        assert result.is_ended is True

    def test_ejected_players_are_not_survivors(self) -> None:
        """追放された keeper は比較する生存人数に含めない。"""
        result = _evaluate(
            _outcomes(dead=(_CREW[0],), ejected=(_KEEPERS[0],))
        )

        assert result.is_ended is False


class TestSurvivingPlayerGroupComparisonValidation:
    """比較条件の不足と開始直後から自明に成立する宣言を構築時に拒否する。"""

    def test_missing_comparison_state_is_rejected(self) -> None:
        """比較先が無い宣言は、右辺の人数が決まらないため拒否する。"""
        with pytest.raises(GameEndConditionValidationException):
            GameEndCondition(
                condition_type=(
                    GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE
                ),
                required_state={"role": "crew"},
            )

    def test_identical_state_selectors_are_rejected(self) -> None:
        """同じ集合との比較は常に成立するため、開始即終了を構築時に拒否する。"""
        with pytest.raises(GameEndConditionValidationException, match="同じ"):
            GameEndCondition(
                condition_type=(
                    GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE
                ),
                required_state={"role": "crew"},
                comparison_state={"role": "crew"},
            )
