"""ALL_MEMBERS_HAVE_OUTCOME が、チームの全員の個人結果だけを見て成立を決めることを保証する (#1516)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
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
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import (
    GameEndCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId

_ALL = [PlayerId(1), PlayerId(2), PlayerId(3), PlayerId(4)]
_NORTH = [PlayerId(1), PlayerId(2)]
_ESCAPED = GameEndCondition(
    condition_type=GameEndConditionTypeEnum.ALL_MEMBERS_HAVE_OUTCOME,
    required_outcome=PlayerOutcomeEnum.RESCUED,
)


def _evaluate(outcomes: dict[int, PlayerOutcomeEnum], members=_NORTH):
    return GameEndConditionEvaluator().evaluate(
        SpotGraphAggregate.empty(SpotGraphId.create(1)),
        _ESCAPED,
        frozenset(),
        _ALL,
        player_outcomes=outcomes,
        team_member_ids=members,
        result_on_match=GameResultEnum.WIN,
    )


class TestDeclaration:
    """成立しえない ALL_MEMBERS_HAVE_OUTCOME を構築時に拒むことを保証する。"""

    def test_missing_outcome_is_rejected(self) -> None:
        """required_outcome を書かないと GameEndConditionValidationException を投げる。"""
        with pytest.raises(GameEndConditionValidationException):
            GameEndCondition(condition_type=GameEndConditionTypeEnum.ALL_MEMBERS_HAVE_OUTCOME)

    def test_unresolved_outcome_is_rejected(self) -> None:
        """required_outcome に UNRESOLVED を書くと GameEndConditionValidationException を投げる。開始した瞬間に成立してしまうため。"""
        with pytest.raises(GameEndConditionValidationException):
            GameEndCondition(
                condition_type=GameEndConditionTypeEnum.ALL_MEMBERS_HAVE_OUTCOME,
                required_outcome=PlayerOutcomeEnum.UNRESOLVED,
            )


class TestEvaluation:
    """チームの全員が指定の個人結果になったときだけ成立することを保証する。"""

    def test_satisfied_when_every_member_has_the_outcome(self) -> None:
        """北の 2 人が RESCUED なら、南が UNRESOLVED のままでも成立する。"""
        result = _evaluate(
            {
                1: PlayerOutcomeEnum.RESCUED,
                2: PlayerOutcomeEnum.RESCUED,
                3: PlayerOutcomeEnum.UNRESOLVED,
                4: PlayerOutcomeEnum.UNRESOLVED,
            }
        )

        assert result.is_ended is True
        assert result.result is GameResultEnum.WIN

    def test_not_satisfied_when_one_member_is_left_behind(self) -> None:
        """北の 1 人だけが RESCUED で、もう 1 人が UNRESOLVED なら成立しない。"""
        result = _evaluate(
            {
                1: PlayerOutcomeEnum.RESCUED,
                2: PlayerOutcomeEnum.UNRESOLVED,
                3: PlayerOutcomeEnum.RESCUED,
                4: PlayerOutcomeEnum.RESCUED,
            }
        )

        assert result.is_ended is False

    def test_other_teams_outcomes_do_not_count(self) -> None:
        """南の 2 人が RESCUED でも、北の誰も RESCUED でなければ北の条件は成立しない。"""
        result = _evaluate(
            {
                1: PlayerOutcomeEnum.DEAD,
                2: PlayerOutcomeEnum.UNRESOLVED,
                3: PlayerOutcomeEnum.RESCUED,
                4: PlayerOutcomeEnum.RESCUED,
            }
        )

        assert result.is_ended is False

    def test_missing_team_member_ids_raises(self) -> None:
        """team_member_ids を渡さずに評価すると GameEndConditionValidationException を投げる。黙って未成立にすると勝敗が永久に決まらないため。"""
        with pytest.raises(GameEndConditionValidationException):
            _evaluate({1: PlayerOutcomeEnum.RESCUED}, members=None)

    def test_empty_team_is_never_satisfied(self) -> None:
        """team_member_ids が空なら成立しない。空集合の全員を成立とみなさない。"""
        result = _evaluate({}, members=[])

        assert result.is_ended is False

    def test_missing_player_outcomes_raises(self) -> None:
        """player_outcomes を渡さずに評価すると GameEndConditionValidationException を投げる。"""
        with pytest.raises(GameEndConditionValidationException):
            GameEndConditionEvaluator().evaluate(
                SpotGraphAggregate.empty(SpotGraphId.create(1)),
                _ESCAPED,
                frozenset(),
                _ALL,
                team_member_ids=_NORTH,
                result_on_match=GameResultEnum.WIN,
            )

    def test_member_missing_from_outcomes_counts_as_not_reached(self) -> None:
        """outcome の表に北の 1 人の行が無ければ、その人は RESCUED ではないとして成立しない。"""
        result = _evaluate({1: PlayerOutcomeEnum.RESCUED})

        assert result.is_ended is False
