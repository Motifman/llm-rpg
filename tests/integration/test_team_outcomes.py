"""2 チームの世界で、チームの勝敗と個人の結果が決まり、trace に渡る形になることを保証する (#1516)。"""

from __future__ import annotations

import json
from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.runtime_config_helpers import runtime_config

_SCENARIO = (
    Path(__file__).resolve().parents[1] / "fixtures" / "scenarios" / "two_teams_lift.json"
)
_FLAG_CONTEXT = WorldFlagMutationContext(
    source=WorldFlagMutationSource.SCENARIO_EVENT,
    actor_player_id=None,
)


def _runtime():
    return create_world_runtime(_SCENARIO)


def _ids(runtime) -> dict[str, object]:
    return {
        runtime.id_mapper.get_str("player", int(pid)): pid
        for pid in runtime.get_player_ids()
    }


def _move_to_lift(runtime, *string_ids: str) -> None:
    ids = _ids(runtime)
    graph = runtime._spot_graph_repo.find_graph()
    lift = SpotId.create(runtime.id_mapper.get_int("spot", "lift"))
    for string_id in string_ids:
        entity_id = EntityId.create(int(ids[string_id]))
        graph.unplace_entity(entity_id)
        graph.place_entity(entity_id, lift)
    runtime._spot_graph_repo.save(graph)


def _depart(runtime, *riders: str):
    _move_to_lift(runtime, *riders)
    runtime._world_flag_state.add("lift_departed", context=_FLAG_CONTEXT)
    runtime.advance_tick()
    return runtime.check_game_end()


def _players_by_string_id(payload) -> dict[str, dict]:
    return {p["player_string_id"]: p for p in payload["players"]}


class TestTeamResults:
    """チームの勝利条件から勝敗が決まり、勝つチームが高々 1 つになることを保証する。"""

    def test_game_continues_before_the_lift_departs(self) -> None:
        """昇降機が出る前は、全員が乗り場にいてもゲームは終わらず、チームの勝敗も無い。"""
        runtime = _runtime()
        _move_to_lift(runtime, "north_1", "north_2", "south_1", "south_2")
        runtime.advance_tick()

        result = runtime.check_game_end()

        assert result.is_ended is False
        assert result.team_results is None

    def test_team_whose_members_all_escaped_wins(self) -> None:
        """北の 2 人だけが乗って昇降機が出ると、北が WIN、南が LOSE で終わる。全体の勝敗は None。"""
        runtime = _runtime()

        result = _depart(runtime, "north_1", "north_2")

        assert result.is_ended is True
        assert result.result is None
        assert result.team_results == {
            "north": GameResultEnum.WIN,
            "south": GameResultEnum.LOSE,
        }

    def test_defector_escapes_but_their_team_loses(self) -> None:
        """南の 1 人が北の 2 人と乗ると、北が WIN、南は LOSE。乗った南の人の個人結果は RESCUED で、勝敗は LOSE。"""
        runtime = _runtime()

        result = _depart(runtime, "north_1", "north_2", "south_1")

        assert result.team_results == {
            "north": GameResultEnum.WIN,
            "south": GameResultEnum.LOSE,
        }
        players = _players_by_string_id(runtime.team_result_trace(result))
        assert players["south_1"]["outcome"] == "RESCUED"
        assert players["south_1"]["result"] == "LOSE"
        assert players["south_2"]["outcome"] == "UNRESOLVED"
        assert players["south_2"]["result"] == "LOSE"

    def test_mixed_riders_end_with_every_team_losing(self) -> None:
        """北 1 人と南 1 人が乗って昇降機が出ると、どのチームも成立せず、end で全チーム LOSE になる。"""
        runtime = _runtime()

        result = _depart(runtime, "north_1", "south_1")

        assert result.is_ended is True
        assert result.team_results == {
            "north": GameResultEnum.LOSE,
            "south": GameResultEnum.LOSE,
        }

    def test_both_teams_escaping_together_is_a_draw(self) -> None:
        """4 人全員が乗ると両チームが同時に成立し、両方 DRAW になる。WIN は出ない。"""
        runtime = _runtime()

        result = _depart(runtime, "north_1", "north_2", "south_1", "south_2")

        assert result.team_results == {
            "north": GameResultEnum.DRAW,
            "south": GameResultEnum.DRAW,
        }

    def test_external_stop_also_decides_team_results(self) -> None:
        """END_ON_ALL_DOWN で止まったときも、北の 2 人が RESCUED なら北が WIN、南が LOSE になる。"""
        runtime = create_world_runtime(_SCENARIO, config=runtime_config(end_on_all_down=True))
        ids = _ids(runtime)
        registry = runtime._player_outcome_registry
        registry.set_outcome(ids["north_1"], PlayerOutcomeEnum.RESCUED)
        registry.set_outcome(ids["north_2"], PlayerOutcomeEnum.RESCUED)
        registry.set_outcome(ids["south_1"], PlayerOutcomeEnum.DEAD)
        registry.set_outcome(ids["south_2"], PlayerOutcomeEnum.DEAD)

        result = runtime.check_game_end()

        assert result.reason.startswith("外的停止 END_ON_ALL_DOWN")
        assert result.team_results == {
            "north": GameResultEnum.WIN,
            "south": GameResultEnum.LOSE,
        }

    def test_external_stop_without_a_winner_makes_every_team_lose(self) -> None:
        """END_ON_ALL_DOWN で止まったとき、どのチームも全員 RESCUED でなければ全チーム LOSE になる。"""
        runtime = create_world_runtime(_SCENARIO, config=runtime_config(end_on_all_down=True))
        ids = _ids(runtime)
        registry = runtime._player_outcome_registry
        for string_id in ("north_1", "south_1"):
            registry.set_outcome(ids[string_id], PlayerOutcomeEnum.RESCUED)
        for string_id in ("north_2", "south_2"):
            registry.set_outcome(ids[string_id], PlayerOutcomeEnum.DEAD)

        result = runtime.check_game_end()

        assert result.reason.startswith("外的停止 END_ON_ALL_DOWN")
        assert result.team_results == {
            "north": GameResultEnum.LOSE,
            "south": GameResultEnum.LOSE,
        }

    def test_werewolf_scenario_keeps_a_single_result(self) -> None:
        """teams の無い station_drill では、終了判定の team_results は None のまま。"""
        runtime = create_world_runtime(Path("data/scenarios/station_drill.json"))

        result = runtime.check_game_end()

        assert runtime.scenario.teams == ()
        assert result.team_results is None


class TestTeamResultTrace:
    """終了時の勝敗を、trace の team_result にそのまま書ける形で返すことを保証する。"""

    def test_payload_lists_each_team_and_each_player(self) -> None:
        """北が勝った回の payload は、チームごとの勝敗と所属、人ごとの所属・個人結果・勝敗を持つ。"""
        runtime = _runtime()
        result = _depart(runtime, "north_1", "north_2")

        payload = runtime.team_result_trace(result)

        teams = {t["team_id"]: t for t in payload["teams"]}
        assert teams["north"]["result"] == "WIN"
        assert teams["north"]["satisfied"] is True
        assert teams["south"]["result"] == "LOSE"
        assert teams["south"]["satisfied"] is False
        assert sorted(teams["north"]["member_player_string_ids"]) == ["north_1", "north_2"]
        players = _players_by_string_id(payload)
        assert players["north_1"] == {
            "player_id": int(_ids(runtime)["north_1"]),
            "player_string_id": "north_1",
            "player_name": "ミナト",
            "team_id": "north",
            "outcome": "RESCUED",
            "result": "WIN",
        }
        assert payload["reason"] == result.reason

    def test_draw_payload_marks_both_teams_satisfied(self) -> None:
        """4 人全員が乗った回の payload は、両チームが DRAW かつ satisfied で、4 人の result も DRAW。理由には両チームの名前が入る。"""
        runtime = _runtime()
        result = _depart(runtime, "north_1", "north_2", "south_1", "south_2")

        payload = runtime.team_result_trace(result)

        assert [(t["result"], t["satisfied"]) for t in payload["teams"]] == [("DRAW", True), ("DRAW", True)]
        assert {p["result"] for p in payload["players"]} == {"DRAW"}
        assert "北の班" in payload["reason"] and "南の班" in payload["reason"]

    def test_losing_payload_says_what_each_team_lacked(self) -> None:
        """北 1 人と南 1 人だけが乗った回の payload は、両チーム LOSE で、それぞれの理由に RESCUED が 1/2 人だったことが残る。"""
        runtime = _runtime()
        result = _depart(runtime, "north_1", "south_1")

        payload = runtime.team_result_trace(result)

        for team in payload["teams"]:
            assert team["result"] == "LOSE" and team["satisfied"] is False
            assert team["reason"] == "チームの RESCUED は 1/2人"
        assert payload["reason"] == "フラグ成立: lift_departed"

    def test_no_payload_while_the_game_continues(self) -> None:
        """終わっていない判定結果からは payload を作らない。"""
        runtime = _runtime()

        assert runtime.team_result_trace(runtime.check_game_end()) is None

    def test_no_payload_for_scenario_without_teams(self, tmp_path: Path) -> None:
        """teams の無いシナリオでは、終わっても payload を作らない。"""
        raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))
        del raw["teams"]
        raw["game_end_conditions"] = {"lose": [{"type": "TICK_LIMIT", "tick_limit": 1}]}
        path = tmp_path / "no_teams.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        runtime = create_world_runtime(path)
        runtime.advance_tick()

        result = runtime.check_game_end()

        assert result.is_ended is True
        assert runtime.team_result_trace(result) is None


def _whole_prompt(runtime, pid) -> str:
    prompt = runtime.build_full_prompt(pid)
    text = "\n".join(str(m["content"]) for m in prompt["messages"])
    return text + json.dumps(prompt["tools"], ensure_ascii=False)


class TestTeamsStayHidden:
    """チームの名前と、相手チームの所属が、プロンプトに出ないことを保証する。

    所属を書いた initial_state のキーは、他の state と同じく本人の「自分の状態」に
    だけ出る (相手には出ない)。
    """

    def test_no_prompt_shows_team_names_or_the_other_side(self) -> None:
        """起動直後、4 人それぞれのプロンプトに、チームの名前も相手チームの所属の値も出ない。自分の所属と仲間の名前は出る。"""
        runtime = _runtime()
        ids = _ids(runtime)
        mates = {"north_1": "トウカ", "north_2": "ミナト", "south_1": "サヤ", "south_2": "ゲンジ"}

        for string_id, pid in ids.items():
            own, other = ("north", "south") if string_id.startswith("north") else ("south", "north")
            text = _whole_prompt(runtime, pid)

            assert f"team={own}" in text and mates[string_id] in text, text
            assert f"team={other}" not in text, text
            assert "北の班" not in text and "南の班" not in text, text

    def test_meeting_the_other_side_does_not_reveal_their_team(self) -> None:
        """北のミナトが南の野営地に入って南の 2 人に会っても、ミナトのプロンプトに南の所属は出ず、南の 2 人のプロンプトにも北の所属は出ない。"""
        runtime = _runtime()
        ids = _ids(runtime)
        graph = runtime._spot_graph_repo.find_graph()
        entity_id = EntityId.create(int(ids["north_1"]))
        graph.unplace_entity(entity_id)
        graph.place_entity(
            entity_id, SpotId.create(runtime.id_mapper.get_int("spot", "camp_south"))
        )
        runtime._spot_graph_repo.save(graph)
        runtime.advance_tick()

        minato = _whole_prompt(runtime, ids["north_1"])
        assert "ゲンジ" in minato and "team=south" not in minato, minato
        for south in ("south_1", "south_2"):
            text = _whole_prompt(runtime, ids[south])
            assert "ミナト" in text and "team=north" not in text, text
