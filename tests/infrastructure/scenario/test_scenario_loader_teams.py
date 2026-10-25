"""シナリオの ``teams`` を読み、所属と勝利条件を組み立てる挙動を保証する (#1516)。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
    GameEndConditionTypeEnum,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoader,
    ScenarioLoadError,
)

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "scenarios" / "two_teams_lift.json"


def _raw() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _load(raw: dict[str, Any], **kwargs: Any):
    return ScenarioLoader().load_from_dict(raw, **kwargs)


def _members_by_team(result) -> dict[str, list[str]]:
    return {
        team.team_id: sorted(result.id_mapper.get_str("player", int(pid)) for pid in team.member_player_ids)
        for team in result.teams
    }


class TestTeamsAreRead:
    """``teams`` の宣言から所属と勝利条件を組み立てることを保証する。"""

    def test_members_come_from_initial_state(self) -> None:
        """initial_state.team が north の 2 人は北の班、south の 2 人は南の班に入る。"""
        result = _load(_raw())

        assert _members_by_team(result) == {
            "north": ["north_1", "north_2"],
            "south": ["south_1", "south_2"],
        }

    def test_win_condition_is_parsed(self) -> None:
        """win の ALL_MEMBERS_HAVE_OUTCOME は、outcome を required_outcome に持つ条件になる。"""
        result = _load(_raw())

        [condition] = result.teams[0].win_conditions
        assert condition.condition_type is GameEndConditionTypeEnum.ALL_MEMBERS_HAVE_OUTCOME
        assert condition.required_outcome is PlayerOutcomeEnum.RESCUED

    def test_neutral_end_with_flag_is_allowed_when_teams_exist(self) -> None:
        """teams のあるシナリオでは、end に FLAG_SET を置ける。"""
        result = _load(_raw())

        [condition] = result.end_conditions
        assert condition.condition_type is GameEndConditionTypeEnum.FLAG_SET

    def test_scenario_without_teams_has_no_teams(self) -> None:
        """teams を書かないシナリオの teams は空になる。"""
        raw = _raw()
        del raw["teams"]
        raw["game_end_conditions"] = {"lose": [{"type": "TICK_LIMIT", "tick_limit": 5}]}

        result = _load(raw)

        assert result.teams == ()

    def test_round_assignment_slots_move_players_between_teams(self) -> None:
        """round_assignment の枠に team を書くと、所属は割り当てたあとの initial_state で決まる。"""
        raw = _raw()
        raw["round_assignment"] = {
            "groups": [
                {
                    "players": ["north_1", "north_2", "south_1", "south_2"],
                    "slots": [
                        {"initial_state": {"team": "north"}},
                        {"initial_state": {"team": "north"}},
                        {"initial_state": {"team": "south"}},
                        {"initial_state": {"team": "south"}},
                    ],
                }
            ]
        }

        rounds = [_members_by_team(_load(copy.deepcopy(raw), random_seed=7, round_number=n)) for n in (1, 2, 3, 4)]

        assert all(sorted(len(m) for m in r.values()) == [2, 2] for r in rounds)
        assert len({json.dumps(r, sort_keys=True) for r in rounds}) > 1


class TestBrokenTeamsAreRejected:
    """勝敗が決まらない、または誰から見た勝ちか曖昧になる宣言を読み込み時に止めることを保証する。"""

    def test_player_in_no_team_is_rejected(self) -> None:
        """どのチームの member_state にも一致しない player がいると ScenarioLoadError を投げる。"""
        raw = _raw()
        raw["players"][3]["initial_state"] = {"team": "west"}

        with pytest.raises(ScenarioLoadError, match="south_2"):
            _load(raw)

    def test_player_in_two_teams_is_rejected(self) -> None:
        """2 つのチームの member_state に同じ人が一致すると、その人の id を挙げて ScenarioLoadError を投げる。"""
        raw = _raw()
        raw["teams"].append(
            {
                "id": "north_again",
                "name": "もう一つの北",
                "member_state": {"team": "north"},
                "win": [{"type": "FLAG_SET", "target_flag": "x"}],
            }
        )

        with pytest.raises(ScenarioLoadError, match="north_1 が teams の north と north_again"):
            _load(raw)

    def test_overlapping_member_state_is_rejected(self) -> None:
        """北の member_state に一致する人が、別のチームの member_state にも一致すると ScenarioLoadError を投げる。"""
        raw = _raw()
        raw["players"][0]["initial_state"] = {"team": "north", "squad": "a"}
        raw["teams"].append(
            {
                "id": "squad_a",
                "name": "a 組",
                "member_state": {"squad": "a"},
                "win": [{"type": "FLAG_SET", "target_flag": "x"}],
            }
        )

        with pytest.raises(ScenarioLoadError, match="north_1"):
            _load(raw)

    def test_boolean_state_does_not_match_number_one(self) -> None:
        """member_state が {"team": 1} のとき、initial_state が {"team": true} の人は所属せず、ScenarioLoadError で挙がる。"""
        raw = _raw()
        raw["players"][0]["initial_state"] = {"team": True}
        raw["teams"][0]["member_state"] = {"team": 1}
        raw["players"][1]["initial_state"] = {"team": 1}

        with pytest.raises(ScenarioLoadError, match="north_1"):
            _load(raw)

    def test_global_win_with_teams_is_rejected(self) -> None:
        """teams と game_end_conditions.win を両方書くと ScenarioLoadError を投げる。"""
        raw = _raw()
        raw["game_end_conditions"]["win"] = [{"type": "FLAG_SET", "target_flag": "x"}]

        with pytest.raises(ScenarioLoadError, match="teams"):
            _load(raw)

    def test_global_lose_with_teams_is_rejected(self) -> None:
        """teams と game_end_conditions.lose を両方書くと ScenarioLoadError を投げる。"""
        raw = _raw()
        raw["game_end_conditions"]["lose"] = [{"type": "TICK_LIMIT", "tick_limit": 9}]

        with pytest.raises(ScenarioLoadError, match="teams"):
            _load(raw)

    def test_members_condition_outside_teams_is_rejected(self) -> None:
        """ALL_MEMBERS_HAVE_OUTCOME を game_end_conditions.end に置くと ScenarioLoadError を投げる。"""
        raw = _raw()
        raw["game_end_conditions"]["end"].append({"type": "ALL_MEMBERS_HAVE_OUTCOME", "outcome": "RESCUED"})

        with pytest.raises(ScenarioLoadError, match="ALL_MEMBERS_HAVE_OUTCOME"):
            _load(raw)

    def test_members_condition_in_scenario_without_teams_is_rejected(self) -> None:
        """teams の無いシナリオで game_end_conditions.win に ALL_MEMBERS_HAVE_OUTCOME を置くと ScenarioLoadError を投げる。"""
        raw = _raw()
        del raw["teams"]
        raw["game_end_conditions"] = {"win": [{"type": "ALL_MEMBERS_HAVE_OUTCOME", "outcome": "RESCUED"}]}

        with pytest.raises(ScenarioLoadError, match="ALL_MEMBERS_HAVE_OUTCOME"):
            _load(raw)

    def test_flag_in_end_without_teams_stays_rejected(self) -> None:
        """teams の無いシナリオでは、これまでどおり end に FLAG_SET を置けない。"""
        raw = _raw()
        del raw["teams"]

        with pytest.raises(ScenarioLoadError, match="FLAG_SET"):
            _load(raw)

    def test_unknown_outcome_is_rejected(self) -> None:
        """ALL_MEMBERS_HAVE_OUTCOME の outcome に知らない値を書くと ScenarioLoadError を投げる。"""
        raw = _raw()
        raw["teams"][0]["win"][0]["outcome"] = "ESCAPED"

        with pytest.raises(ScenarioLoadError, match="ESCAPED"):
            _load(raw)

    def test_missing_outcome_is_rejected(self) -> None:
        """ALL_MEMBERS_HAVE_OUTCOME に outcome を書かないと ScenarioLoadError を投げる。"""
        raw = _raw()
        del raw["teams"][0]["win"][0]["outcome"]

        with pytest.raises(ScenarioLoadError, match="outcome"):
            _load(raw)

    def test_duplicated_team_id_is_rejected(self) -> None:
        """同じ id のチームを 2 つ書くと ScenarioLoadError を投げる。"""
        raw = _raw()
        raw["teams"][1]["id"] = "north"

        with pytest.raises(ScenarioLoadError, match="north"):
            _load(raw)

    def test_single_team_is_rejected(self) -> None:
        """チームが 1 つだけだと ScenarioLoadError を投げる。相手のいない勝敗は全体の win と変わらないため。"""
        raw = _raw()
        raw["teams"] = raw["teams"][:1]
        for player in raw["players"]:
            player["initial_state"] = {"team": "north"}

        with pytest.raises(ScenarioLoadError, match="2 つ以上"):
            _load(raw)

    def test_unknown_team_key_is_rejected(self) -> None:
        """チームに知らないキーを書くと ScenarioLoadError を投げる。"""
        raw = _raw()
        raw["teams"][0]["members"] = ["north_1"]

        with pytest.raises(ScenarioLoadError, match="members"):
            _load(raw)

    def test_empty_member_state_is_rejected(self) -> None:
        """member_state が空のチームを書くと ScenarioLoadError を投げる。全員に一致してしまうため。"""
        raw = _raw()
        raw["teams"][0]["member_state"] = {}

        with pytest.raises(ScenarioLoadError, match="member_state"):
            _load(raw)

    def test_empty_win_is_rejected(self) -> None:
        """win が空のチームを書くと ScenarioLoadError を投げる。"""
        raw = _raw()
        raw["teams"][0]["win"] = []

        with pytest.raises(ScenarioLoadError, match="勝利条件を 1 つ以上"):
            _load(raw)

    def test_place_condition_in_team_win_is_rejected(self) -> None:
        """teams[].win に ALL_AT_SPOT を置くと ScenarioLoadError を投げる。世界全体を数えるので「チームの全員が」と読み違えるため。"""
        raw = _raw()
        raw["teams"][0]["win"] = [{"type": "ALL_AT_SPOT", "target_spot": "lift"}]

        with pytest.raises(ScenarioLoadError, match="teams\\[\\]\\.win に ALL_AT_SPOT は置けません"):
            _load(raw)

    def test_teams_without_end_are_rejected(self) -> None:
        """teams を書いて game_end_conditions.end を書かないと ScenarioLoadError を投げる。どのチームも勝たない終わり方が無いと、勝敗が決まらないまま打ち切られるため。"""
        raw = _raw()
        raw["game_end_conditions"] = {}

        with pytest.raises(ScenarioLoadError, match="game_end_conditions.end を 1 つ以上"):
            _load(raw)

    def test_waiting_for_outcome_no_rule_gives_is_rejected(self) -> None:
        """win が全員の RESCUED を待つのに、RESCUED を付ける player_outcome_rules が無いと ScenarioLoadError を投げる。"""
        raw = _raw()
        raw["player_outcome_rules"][0]["outcome"] = "STRANDED"

        with pytest.raises(ScenarioLoadError, match="RESCUED を付ける規則がありません"):
            _load(raw)

    def test_waiting_for_death_needs_no_rule(self) -> None:
        """win が相手ではなく全員の DEAD を待つ形でも、DEAD は死が付けるので player_outcome_rules が無くても読める。"""
        raw = _raw()
        raw["teams"][1]["win"] = [{"type": "ALL_MEMBERS_HAVE_OUTCOME", "outcome": "DEAD"}]

        result = _load(raw)

        assert result.teams[1].win_conditions[0].required_outcome is PlayerOutcomeEnum.DEAD
