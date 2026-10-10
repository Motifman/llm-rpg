"""ScenarioTeam の宣言の不変条件と、成立したチームから勝敗を決める規則を保証する (#1516)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
    GameEndConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ScenarioTeamValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import (
    GameEndCondition,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_team import (
    ScenarioTeam,
    decide_team_results,
)

_ESCAPED = GameEndCondition(
    condition_type=GameEndConditionTypeEnum.ALL_MEMBERS_HAVE_OUTCOME,
    required_outcome=PlayerOutcomeEnum.RESCUED,
)


def _team(team_id: str, *members: int) -> ScenarioTeam:
    return ScenarioTeam(
        team_id=team_id,
        name=f"チーム{team_id}",
        member_player_ids=tuple(PlayerId(m) for m in members),
        win_conditions=(_ESCAPED,),
    )


class TestScenarioTeamDeclaration:
    """勝敗が決まらないチームを構築時に拒むことを保証する。"""

    def test_team_without_members_is_rejected(self) -> None:
        """所属する人が 0 人のチームを作ると ScenarioTeamValidationException を投げる。全員が条件を満たす、が空集合で成立してしまうため。"""
        with pytest.raises(ScenarioTeamValidationException):
            _team("north")

    def test_team_without_win_conditions_is_rejected(self) -> None:
        """勝利条件が 1 つも無いチームを作ると ScenarioTeamValidationException を投げる。"""
        with pytest.raises(ScenarioTeamValidationException):
            ScenarioTeam(
                team_id="north",
                name="チーム北",
                member_player_ids=(PlayerId(1),),
                win_conditions=(),
            )

    def test_duplicated_member_is_rejected(self) -> None:
        """同じ player を 2 度含むチームを作ると ScenarioTeamValidationException を投げる。"""
        with pytest.raises(ScenarioTeamValidationException):
            _team("north", 1, 1)

    def test_blank_team_id_is_rejected(self) -> None:
        """空白だけの team_id を渡すと ScenarioTeamValidationException を投げる。"""
        with pytest.raises(ScenarioTeamValidationException):
            _team("  ", 1)


class TestDecideTeamResults:
    """成立したチームの集合から、勝つチームが高々 1 つになるよう勝敗を決めることを保証する。"""

    def test_single_satisfied_team_wins_and_others_lose(self) -> None:
        """成立したのが北だけなら、北が WIN、南が LOSE になる。"""
        teams = (_team("north", 1, 2), _team("south", 3, 4))

        results = decide_team_results(teams, frozenset({"north"}))

        assert results == {"north": GameResultEnum.WIN, "south": GameResultEnum.LOSE}

    def test_no_satisfied_team_means_every_team_loses(self) -> None:
        """どのチームも成立していなければ、全チームが LOSE になる。"""
        teams = (_team("north", 1, 2), _team("south", 3, 4))

        results = decide_team_results(teams, frozenset())

        assert results == {"north": GameResultEnum.LOSE, "south": GameResultEnum.LOSE}

    def test_simultaneous_satisfaction_is_a_draw_not_two_wins(self) -> None:
        """北と南が同時に成立したら両方 DRAW になり、成立しなかった東は LOSE。WIN は 1 つも出ない。"""
        teams = (_team("north", 1), _team("south", 2), _team("east", 3))

        results = decide_team_results(teams, frozenset({"north", "south"}))

        assert results == {
            "north": GameResultEnum.DRAW,
            "south": GameResultEnum.DRAW,
            "east": GameResultEnum.LOSE,
        }

    def test_unknown_satisfied_team_id_is_rejected(self) -> None:
        """宣言に無い team_id を成立したと渡すと ScenarioTeamValidationException を投げる。"""
        teams = (_team("north", 1), _team("south", 2))

        with pytest.raises(ScenarioTeamValidationException):
            decide_team_results(teams, frozenset({"west"}))
