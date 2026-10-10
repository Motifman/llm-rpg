"""``teams``: チームの所属と勝利条件を読む (#1516)。

所属は名簿ではなく ``member_state`` で書く。``round_assignment`` の枠が書き換える
のは ``initial_state`` なので、枠に所属の値を書けば回ごとの組み分けがそのまま効く。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
    GameEndConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ScenarioTeamValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.player_outcome_rule import (
    PlayerOutcomeRule,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_team import ScenarioTeam
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.models import PlayerSpawnConfig
from ai_rpg_world.infrastructure.scenario.parse_helpers import reject_unknown_keys
from ai_rpg_world.infrastructure.scenario.parse_world import parse_end_conditions
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper

_TEAM_KEYS = ("id", "name", "member_state", "win")


def parse_teams(
    raw: Any,
    players: Sequence[PlayerSpawnConfig],
    mapper: ScenarioIdMapper,
) -> tuple[ScenarioTeam, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or len(raw) < 2:
        raise ScenarioLoadError(
            "teams は 2 つ以上のチームの配列で書いてください。"
            "相手のいない勝敗は game_end_conditions.win と変わりません"
        )
    teams: list[ScenarioTeam] = []
    seen_ids: set[str] = set()
    team_of_player: dict[str, str] = {}
    for index, team_raw in enumerate(raw):
        where = f"teams[{index}]"
        if not isinstance(team_raw, Mapping):
            raise ScenarioLoadError(f"{where} は object で書いてください")
        reject_unknown_keys(team_raw, _TEAM_KEYS, where=where)
        team_id = team_raw.get("id")
        if not isinstance(team_id, str) or not team_id.strip():
            raise ScenarioLoadError(f"{where}.id は空でない文字列にしてください")
        if team_id in seen_ids:
            raise ScenarioLoadError(f"teams の id {team_id!r} が重複しています")
        seen_ids.add(team_id)
        name = team_raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ScenarioLoadError(f"{where}.name は空でない文字列にしてください")
        member_state = team_raw.get("member_state")
        if not isinstance(member_state, Mapping) or not member_state:
            raise ScenarioLoadError(
                f"{where}.member_state は空でない object で書いてください"
                " (空だと全員に一致します)"
            )
        win_raw = team_raw.get("win")
        if not isinstance(win_raw, list) or not win_raw:
            raise ScenarioLoadError(
                f"{where}.win に勝利条件を 1 つ以上書いてください"
            )
        members: list[PlayerSpawnConfig] = []
        for player in players:
            if not _matches(player.initial_state, member_state):
                continue
            other = team_of_player.get(player.string_id)
            if other is not None:
                raise ScenarioLoadError(
                    f"player {player.string_id} が teams の {other} と {team_id} の"
                    " 両方に所属しています"
                )
            team_of_player[player.string_id] = team_id
            members.append(player)
        try:
            teams.append(
                ScenarioTeam(
                    team_id=team_id,
                    name=name,
                    member_player_ids=tuple(PlayerId(p.player_id) for p in members),
                    win_conditions=tuple(
                        parse_end_conditions(win_raw, mapper, section="team_win")
                    ),
                )
            )
        except ScenarioTeamValidationException as exc:
            raise ScenarioLoadError(f"{where}: {exc}") from exc
    unassigned = [p.string_id for p in players if p.string_id not in team_of_player]
    if unassigned:
        raise ScenarioLoadError(
            f"どのチームにも所属しない player があります: {unassigned}"
            " (勝敗が決まりません)"
        )
    return tuple(teams)


# RESCUED / STRANDED は player_outcome_rules からしか付かない。DEAD と EJECTED は
# 死と会議の投票が付けるので、規則が無くても届く。
_OUTCOMES_FROM_RULES_ONLY = frozenset(
    {PlayerOutcomeEnum.RESCUED, PlayerOutcomeEnum.STRANDED}
)


def reject_unreachable_team_outcomes(
    teams: Sequence[ScenarioTeam],
    rules: Sequence[PlayerOutcomeRule],
) -> None:
    """どの規則も付けない個人結果を待つチームの勝利条件を止める。"""
    produced = {rule.outcome for rule in rules}
    for team in teams:
        for condition in team.win_conditions:
            if condition.condition_type is not GameEndConditionTypeEnum.ALL_MEMBERS_HAVE_OUTCOME:
                continue
            outcome = condition.required_outcome
            if outcome in _OUTCOMES_FROM_RULES_ONLY and outcome not in produced:
                raise ScenarioLoadError(
                    f"teams の {team.team_id} の win は全員の {outcome.value} を"
                    " 待ちますが、player_outcome_rules に"
                    f" {outcome.value} を付ける規則がありません"
                )


def _matches(state: Mapping[str, Any], required: Mapping[str, Any]) -> bool:
    # True == 1 で別の値が一致しないよう、真偽値かどうかもそろえる。
    return all(
        key in state
        and state[key] == value
        and isinstance(state[key], bool) == isinstance(value, bool)
        for key, value in required.items()
    )
