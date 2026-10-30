"""廃坑の山村 (`mine_village_v1`) の勝ち負けが、チーム単位で決まることを保証する。

設計は docs/mine_village_scenario_design.md の「人数と勝ち負け」: チームの 2 人とも
昇降機で脱出したチームの勝ち。寝返って 1 人だけ脱出しても、その人のチームは負け。
両方のチームが勝つ結果は無い。チームの書き方は design_decisions D1516。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import InteractionNotAllowedException
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"

_PLAYERS = {"haru": PlayerId(1), "mio": PlayerId(2), "gen": PlayerId(3), "sayo": PlayerId(4)}
_TEAM_OF = {"haru": "north", "mio": "north", "gen": "south", "sayo": "south"}
_TEAM_NAMES = ("チーム北", "チーム南")
_WARM_TICKS = 6
_SAFE_CODE = "1907"


def _raw() -> dict[str, Any]:
    return json.loads(_SCENARIO.read_text(encoding="utf-8"))


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _place(runtime, string_id: str, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(_PLAYERS[string_id]))
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(runtime.id_mapper.get_int("spot", spot)))
    runtime._spot_graph_repo.save(graph)


def _act(runtime, string_id: str, spot: str, obj: str, action: str, **params: str) -> None:
    _place(runtime, string_id, spot)
    runtime.do_interact(_PLAYERS[string_id], obj, action, interaction_parameters=params or None)


def _ready_the_lift(runtime) -> None:
    """ハルが起動鍵を手に入れ、発電機に燃料を入れて動かし、温まるまで待つ。"""
    _act(runtime, "haru", "company_office", "office_safe", "open_safe", code=_SAFE_CODE)
    _act(runtime, "haru", "machine_room", "generator", "pour_fuel_can")
    runtime.advance_tick()
    _act(runtime, "haru", "machine_room", "generator", "start_generator")
    for _ in range(_WARM_TICKS + 1):
        runtime.advance_tick()


def _board(runtime, string_id: str) -> None:
    _act(runtime, string_id, "lift_landing", "lift", "board_lift")


def _launch(runtime):
    """籠に乗っていない人を機械室に置き、籠の中のハルが昇降機を動かして、次の tick の終了判定を返す。"""
    for string_id, pid in _PLAYERS.items():
        if runtime._player_status_repo.find_by_id(pid).state.get("aboard") != "yes":
            _place(runtime, string_id, "machine_room")
    runtime.do_interact(_PLAYERS["haru"], "lift", "start_lift")
    runtime.advance_tick()
    return runtime.check_game_end()


def _depart_with(runtime, *riders: str):
    """鍵と温まった発電機をそろえ、riders を順に籠に乗り込ませてから昇降機を動かし、次の tick の終了判定を返す。riders の先頭はハル。"""
    _ready_the_lift(runtime)
    for string_id in riders:
        _board(runtime, string_id)
    return _launch(runtime)


def _players_in(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["player_string_id"]: p for p in payload["players"]}


class TestTeamsAreDeclaredWithoutRoles:
    """チームの所属を role 以外の欄で書き、勝ち負けをチームの勝利条件だけで決めることを保証する。"""

    def test_each_player_belongs_to_the_team_of_their_entrance(self) -> None:
        """北の竪坑口から入るハルとミオは team=north、南の横坑口から入るゲンとサヨは team=south を持ち、role は書かない。"""
        players = {p["id"]: p for p in _raw()["players"]}

        assert {sid: p["initial_state"]["team"] for sid, p in players.items()} == _TEAM_OF
        assert all("role" not in p["initial_state"] for p in players.values())

    def test_both_teams_win_only_when_all_members_escape(self) -> None:
        """北と南の 2 チームがあり、どちらも勝利条件は「チームの全員が RESCUED」の 1 つだけ。"""
        teams = _raw()["teams"]

        assert [(t["id"], t["member_state"], t["win"]) for t in teams] == [
            (team, {"team": team}, [{"type": "ALL_MEMBERS_HAVE_OUTCOME", "outcome": "RESCUED"}])
            for team in ("north", "south")
        ]

    def test_game_end_has_no_overall_win_or_lose(self) -> None:
        """全体の win / lose を置かず、終わりは全員の個人結果が決まったときだけ。締め切りの TICK_LIMIT を置かない。"""
        assert _raw()["game_end_conditions"] == {"end": [{"type": "ALL_PLAYER_OUTCOMES_RESOLVED"}]}

    def test_runtime_reads_both_teams(self, runtime) -> None:
        """読み込んだシナリオに、北と南の 2 チームが並ぶ。"""
        assert [t.team_id for t in runtime.scenario.teams] == ["north", "south"]


class TestTeamResultsFollowTheLift:
    """昇降機が出たときに乗り場にいた人から、チームの勝敗が決まることを保証する。"""

    def test_nothing_is_decided_before_the_lift_departs(self, runtime) -> None:
        """昇降機が出る前は、4 人とも乗り場にいてもゲームは終わらず、チームの勝敗も無い。"""
        for string_id in _PLAYERS:
            _place(runtime, string_id, "lift_landing")
        runtime.advance_tick()

        result = runtime.check_game_end()

        assert result.is_ended is False
        assert result.team_results is None

    def test_north_wins_when_both_of_them_escape(self, runtime) -> None:
        """北の 2 人だけが乗って昇降機が出ると、北が WIN、南が LOSE で終わり、全体の勝敗は無い。"""
        result = _depart_with(runtime, "haru", "mio")

        assert result.is_ended is True
        assert result.result is None
        assert result.team_results == {"north": GameResultEnum.WIN, "south": GameResultEnum.LOSE}

    def test_defector_escapes_but_their_team_loses(self, runtime) -> None:
        """南のゲンが北の 2 人と乗ると、北が WIN、南は LOSE。ゲンの個人結果は RESCUED で、勝敗は LOSE。"""
        result = _depart_with(runtime, "haru", "mio", "gen")

        assert result.team_results == {"north": GameResultEnum.WIN, "south": GameResultEnum.LOSE}
        players = _players_in(runtime.team_result_trace(result))
        assert (players["gen"]["outcome"], players["gen"]["result"]) == ("RESCUED", "LOSE")
        assert (players["sayo"]["outcome"], players["sayo"]["result"]) == ("STRANDED", "LOSE")

    def test_mixed_riders_make_every_team_lose(self, runtime) -> None:
        """北のハルと南のゲンだけが乗ると、どちらのチームも全員そろわず、両チーム LOSE で終わる。"""
        result = _depart_with(runtime, "haru", "gen")

        assert result.is_ended is True
        assert result.team_results == {"north": GameResultEnum.LOSE, "south": GameResultEnum.LOSE}

    def test_the_cage_holds_three_so_both_teams_never_escape_together(self, runtime) -> None:
        """4 人とも乗り込もうとしても、籠の定員 3 人で 4 人目のサヨは乗れず、北が WIN、南が LOSE になる。両チームが同時に成立する回は無い。"""
        _ready_the_lift(runtime)
        for string_id in ("haru", "mio", "gen"):
            _board(runtime, string_id)

        with pytest.raises(InteractionNotAllowedException, match="いっぱい"):
            _board(runtime, "sayo")
        result = _launch(runtime)

        assert result.team_results == {"north": GameResultEnum.WIN, "south": GameResultEnum.LOSE}


class TestTeamResultIsTraced:
    """終了時に、チームの勝敗と人ごとの所属・個人結果を trace の team_result に書ける形で返すことを保証する。"""

    def test_payload_names_the_teams_and_who_was_in_each(self, runtime) -> None:
        """北が勝った回の payload は、チームの名前・勝敗・所属の 2 人と、人ごとの所属・個人結果・勝敗を持つ。"""
        result = _depart_with(runtime, "haru", "mio")

        payload = runtime.team_result_trace(result)

        teams = {t["team_id"]: t for t in payload["teams"]}
        assert {tid: (t["name"], t["result"]) for tid, t in teams.items()} == {
            "north": ("チーム北", "WIN"),
            "south": ("チーム南", "LOSE"),
        }
        assert sorted(teams["north"]["member_player_string_ids"]) == ["haru", "mio"]
        assert {sid: (p["team_id"], p["outcome"], p["result"]) for sid, p in _players_in(payload).items()} == {
            "haru": ("north", "RESCUED", "WIN"),
            "mio": ("north", "RESCUED", "WIN"),
            "gen": ("south", "STRANDED", "LOSE"),
            "sayo": ("south", "STRANDED", "LOSE"),
        }


def _whole_prompt(runtime, string_id: str) -> str:
    prompt = runtime.build_full_prompt(_PLAYERS[string_id])
    text = "\n".join(str(m.get("content", "")) for m in prompt["messages"])
    return text + json.dumps(prompt["tools"], ensure_ascii=False)


class TestTeamsStayHiddenAtStart:
    """チームを書いても、相手の存在を伏せる設定とぶつからないことを保証する。"""

    @pytest.mark.parametrize("viewer", sorted(_PLAYERS))
    def test_start_prompt_shows_neither_the_other_side_nor_any_team(self, runtime, viewer) -> None:
        """開始時のプロンプト全文とツールに、相手チームの 2 人の名前、チームの名前、所属のキー `team=` が出ない。仲間の名前は出る。"""
        names = {p["id"]: p["name"] for p in _raw()["players"]}
        mine = _TEAM_OF[viewer]

        text = _whole_prompt(runtime, viewer)

        assert [names[s] for s, t in _TEAM_OF.items() if t != mine and names[s] in text] == []
        assert [names[s] for s, t in _TEAM_OF.items() if t == mine and s != viewer and names[s] not in text] == []
        assert "team=" not in text
        assert [n for n in _TEAM_NAMES if n in text] == []

    def test_team_key_shows_up_as_own_state_without_the_hidden_declaration(self, tmp_path) -> None:
        """`player_attributes.team` の宣言を外すと、ハルの「自分の状態」に `team=north` が出る。所属が伏せられているのが、この宣言のおかげであることを確かめる。"""
        raw = _raw()
        del raw["player_attributes"]["team"]
        if not raw["player_attributes"]:
            del raw["player_attributes"]
        path = tmp_path / "mine_village_without_hidden_team.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        text = _whole_prompt(create_world_runtime(path), "haru")

        assert "team=north" in text

    def test_team_key_does_not_add_a_faction_count_to_the_briefing(self, runtime) -> None:
        """所属を書いても、世界の説明に「参加者は 4 人。内訳は …」の行が出ない。役を 2 種類にすると出る行で、何人いる世界かが分かる。"""
        text = _whole_prompt(runtime, "haru")

        assert "参加者は" not in text
