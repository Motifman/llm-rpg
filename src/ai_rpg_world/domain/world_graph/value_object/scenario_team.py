"""シナリオが宣言するチームと、成立したチームから勝敗を決める規則 (#1516)。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ScenarioTeamValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import (
    GameEndCondition,
)


@dataclass(frozen=True)
class ScenarioTeam:
    """所属する人と勝利条件を持つチーム。

    所属は回の開始時に決まり、回の途中では変わらない。
    """

    team_id: str
    name: str
    member_player_ids: tuple[PlayerId, ...]
    win_conditions: tuple[GameEndCondition, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.team_id, str) or not self.team_id.strip():
            raise ScenarioTeamValidationException(
                "ScenarioTeam.team_id は空でない文字列にしてください"
            )
        if not isinstance(self.name, str) or not self.name.strip():
            raise ScenarioTeamValidationException(
                f"チーム {self.team_id} の name は空でない文字列にしてください"
            )
        if not self.member_player_ids:
            raise ScenarioTeamValidationException(
                f"チーム {self.team_id} に所属する人がいません"
            )
        if len(set(self.member_player_ids)) != len(self.member_player_ids):
            raise ScenarioTeamValidationException(
                f"チーム {self.team_id} に同じ人が重複しています"
            )
        if not self.win_conditions:
            raise ScenarioTeamValidationException(
                f"チーム {self.team_id} に勝利条件がありません"
            )


def decide_team_results(
    teams: Iterable[ScenarioTeam],
    satisfied_team_ids: frozenset[str],
) -> Mapping[str, GameResultEnum]:
    """勝利条件が成立したチームの集合から、各チームの勝敗を決める。

    同時に 2 チーム以上が成立したら、どれも勝ちにしない (DRAW)。勝つチームが
    常に高々 1 つになるので、次の回へ「両方とも勝った」が持ち越されない。
    """
    team_ids = [team.team_id for team in teams]
    unknown = satisfied_team_ids - set(team_ids)
    if unknown:
        raise ScenarioTeamValidationException(
            f"宣言に無いチームが成立したことになっています: {sorted(unknown)}"
        )
    on_match = (
        GameResultEnum.WIN if len(satisfied_team_ids) == 1 else GameResultEnum.DRAW
    )
    return {
        team_id: on_match if team_id in satisfied_team_ids else GameResultEnum.LOSE
        for team_id in team_ids
    }
