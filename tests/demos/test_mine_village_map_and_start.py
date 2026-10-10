"""廃坑の山村 (`mine_village_v1`) の地図と開始の状態が、設計どおりであることを保証する。

設計は docs/mine_village_scenario_design.md、座標とつなぎ方の正は
docs/mine_village_map.json。2 チームは互いの存在を知らずに始まるので、
相手の名前や役の内訳がプロンプトに出る経路をシナリオの側で塞いでいることも見る。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.scenario.spot_map_validator import (
    KeySpotRequirement,
    MapValidationConfig,
    validate_spot_map,
)

_REPO = Path(__file__).resolve().parents[2]
_SCENARIO = _REPO / "data" / "scenarios" / "mine_village_v1.json"
_MAP = _REPO / "docs" / "mine_village_map.json"

_TEAMS = {
    "north": {"spawn": "north_shaft_head", "players": ("haru", "mio")},
    "south": {"spawn": "south_adit_mouth", "players": ("gen", "sayo")},
}
_KEY_SPOTS = ("lift_landing", "machine_room", "company_office")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def scenario() -> dict[str, Any]:
    return _load(_SCENARIO)


@pytest.fixture(scope="module")
def skeleton() -> dict[str, Any]:
    return _load(_MAP)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _player_id(raw: dict[str, Any], string_id: str) -> PlayerId:
    """players の宣言順に 1 から振られる番号を引く。"""
    ids = [p["id"] for p in raw["players"]]
    return PlayerId(ids.index(string_id) + 1)


def pid_entity(pid: PlayerId) -> EntityId:
    return EntityId.create(int(pid))


def _team_of(string_id: str) -> str:
    return next(team for team, t in _TEAMS.items() if string_id in t["players"])


def _names(raw: dict[str, Any]) -> dict[str, str]:
    return {p["id"]: p["name"] for p in raw["players"]}


class TestMapFollowsTheSkeleton:
    """シナリオの spot と通路が、検算済みの骨組みと同じ配置・つなぎ方であることを保証する。"""

    def test_spots_have_the_skeleton_ids_and_positions(self, scenario, skeleton) -> None:
        """21 か所の id と座標が docs/mine_village_map.json と一致する。"""
        expected = {s["id"]: s["position"] for s in skeleton["spots"]}
        actual = {s["id"]: s["position"] for s in scenario["spots"]}

        assert len(expected) == 21
        assert {k: (float(v["x"]), float(v["y"])) for k, v in actual.items()} == {
            k: (float(v["x"]), float(v["y"])) for k, v in expected.items()
        }

    def test_connections_join_the_same_spots_in_the_same_ticks(self, scenario, skeleton) -> None:
        """31 本の通路が、骨組みと同じ id・両端・移動 tick を持つ。"""
        def shape(raw: dict[str, Any]) -> dict[str, tuple[str, str, int]]:
            return {c["id"]: (c["from"], c["to"], int(c["travel_ticks"])) for c in raw["connections"]}

        assert len(skeleton["connections"]) == 31
        assert shape(scenario) == shape(skeleton)

    def test_every_connection_can_be_walked_both_ways(self, scenario) -> None:
        """一方通行の通路は置かない。閉じ込めは閂と水で作る。"""
        assert all(c.get("is_bidirectional", True) for c in scenario["connections"])

    @pytest.mark.parametrize("team", sorted(_TEAMS))
    def test_spot_map_validator_passes_from_each_team_start(self, scenario, team) -> None:
        """各チームの開始地点から、乗り場・機械室・事務所を重要地点として、警告も誤りに数える厳しい判定 (strict) で検査して ok になる。

        竪坑と横坑は地下を横にずらして描いたので、座標の距離と移動 tick が食い違う。
        この 2 本の食い違いは scripts/check_mine_village_map.py と同じく除いて見る。
        中層の分岐を失うと掘り場が切り離される警告も、意図した行き止まりなので除く。
        """
        vertical = {"north_shaft", "south_adit"}

        result = validate_spot_map(
            scenario,
            MapValidationConfig(
                start_spot_id=_TEAMS[team]["spawn"],
                key_spots=tuple(KeySpotRequirement(s, "error") for s in _KEY_SPOTS),
                strict=True,
                distance_to_tick_ratio=2.0,
            ),
        )

        unexpected = [
            i
            for i in result.errors + result.warnings
            if not (i.code == "TRAVEL_TICKS_DISTANCE_MISMATCH" and i.connection in vertical)
            and not (i.code == "ARTICULATION_SPOT" and i.spots == ("mid_junction",))
        ]
        excused_mismatches = sorted(
            i.connection for i in result.warnings if i.code == "TRAVEL_TICKS_DISTANCE_MISMATCH"
        )
        assert result.ok, result.errors
        assert unexpected == []
        assert excused_mismatches == sorted(vertical)


def _map_check_script():
    spec = importlib.util.spec_from_file_location("check_mine_village_map", _REPO / "scripts" / "check_mine_village_map.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestEachTeamCanWinWithinTheRunLimit:
    """どちらのチームも、開始地点から鍵・燃料・発電機・籠を経て脱出するまでの最短の tick が、実 run の上限 (40) に収まることを保証する。数え方は scripts/check_mine_village_map.py の win_path_ticks。"""

    @pytest.mark.parametrize("path", ["北 (乗り場で鍵を知る)", "北 (鍵と番号を知っている)", "南"])
    def test_shortest_escape_fits_the_run_limit(self, scenario, path) -> None:
        """北が乗り場の張り紙で鍵を知ってから事務所へ取りに戻る道も含め、3 通りとも 40 tick 以内に脱出が決まる。"""
        script = _map_check_script()

        ticks = script.win_path_ticks(scenario["connections"])[path]

        assert ticks <= script.RUN_TICK_LIMIT == 40

    def test_north_discovering_the_key_is_slower_than_south(self, scenario) -> None:
        """鍵のありかと番号を知っている南のほうが、乗り場で知る北より先に脱出できる。南が先に事務所へ寄る得を残す。"""
        ticks = _map_check_script().win_path_ticks(scenario["connections"])

        assert ticks["南"] < ticks["北 (乗り場で鍵を知る)"]


class TestTeamsStartApartAndUnaware:
    """2 チームが別々の入口から、互いを知らずに始まることを保証する。"""

    def test_scenario_loads(self, runtime) -> None:
        """create_world_runtime で読み込めて、4 人が並ぶ。"""
        assert len(runtime.get_player_ids()) == 4

    @pytest.mark.parametrize("team", sorted(_TEAMS))
    def test_each_team_spawns_at_its_own_entrance(self, scenario, runtime, team) -> None:
        """北の 2 人は北の竪坑口、南の 2 人は南の横坑口に置かれる。"""
        graph = runtime._spot_graph_repo.find_graph()
        expected_spot = runtime.id_mapper.get_int("spot", _TEAMS[team]["spawn"])

        for string_id in _TEAMS[team]["players"]:
            pid = _player_id(scenario, string_id)
            assert graph.get_entity_spot(pid_entity(pid)).value == expected_spot

    def test_knows_at_start_lists_only_the_teammate(self, scenario) -> None:
        """各プレイヤーの knows_at_start は、同じチームのもう 1 人だけを並べる。"""
        for player in scenario["players"]:
            team = _TEAMS[_team_of(player["id"])]["players"]
            assert player["knows_at_start"] == [p for p in team if p != player["id"]]

    def test_runtime_introduces_only_the_teammate(self, scenario, runtime) -> None:
        """起動後の知り合いの記録で、各自は味方だけを知っていて、相手チームの 2 人は知らない。"""
        names = _names(scenario)
        for player in scenario["players"]:
            pid = _player_id(scenario, player["id"])
            known = {
                n for sid, n in names.items()
                if sid != player["id"] and runtime._player_acquaintances.find(pid, n) is not None
            }
            mine = _team_of(player["id"])
            assert known == {names[p] for p in _TEAMS[mine]["players"] if p != player["id"]}

    @pytest.mark.parametrize("viewer", ["haru", "mio", "gen", "sayo"])
    def test_start_prompt_names_no_one_from_the_other_team(self, scenario, runtime, viewer) -> None:
        """開始時のプロンプト全文に、相手チームの 2 人の名前が出ず、味方の名前は出る。"""
        names = _names(scenario)
        mine = _team_of(viewer)
        others = [names[p] for t, v in _TEAMS.items() if t != mine for p in v["players"]]
        mate = next(names[p] for p in _TEAMS[mine]["players"] if p != viewer)

        prompt = runtime.build_full_prompt(_player_id(scenario, viewer))
        text = "\n".join(str(m.get("content", "")) for m in prompt["messages"])

        assert [n for n in others if n in text] == []
        assert mate in text


def _place(runtime, pid: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity = pid_entity(pid)
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(runtime.id_mapper.get_int("spot", spot)))
    runtime._spot_graph_repo.save(graph)


def _atmosphere_line(runtime, pid: PlayerId) -> str:
    text = runtime.build_full_prompt(pid)["messages"][1]["content"]
    return next(line for line in text.splitlines() if line.startswith("雰囲気:"))


class TestWorldLooksLikeASnowboundMine:
    """雪の地上と、灯りが無いと見えない地下が、プロンプトにそのとおり出ることを保証する。"""

    def test_surface_shows_snow_not_the_default_fog(self, scenario, runtime) -> None:
        """地上の開始地点で、天候は雪と出る。天候を無効にすると初期値が読まれず霧に倒れるため、有効にしてある。"""
        text = runtime.build_full_prompt(_player_id(scenario, "haru"))["messages"][1]["content"]

        assert "天候: 雪" in text

    def test_a_lit_lamp_turns_the_dark_mine_dim(self, scenario, runtime) -> None:
        """地下の機械室で、灯す前のカンテラでは暗く、油を足して灯すと薄暗く見える。"""
        haru = _player_id(scenario, "haru")
        _place(runtime, haru, "machine_room")
        unlit = _atmosphere_line(runtime, haru)

        runtime.do_interact_with_item(haru, ItemSpecId(runtime.id_mapper.get_int("item_spec", "lamp")), "light_lamp")
        lit = _atmosphere_line(runtime, haru)

        assert "明るさ: 暗い" in unlit
        assert "明るさ: 薄暗い" in lit


class TestScenarioDoesNotRevealTheOtherTeam:
    """相手の存在を伏せるために、シナリオの側で決めることを守っていることを保証する。"""

    def test_no_second_role_and_no_duty(self, scenario) -> None:
        """initial_state.role は 2 種類以上にせず、duty を使わない。役の内訳や担当が全員に出るため。"""
        roles = {p.get("initial_state", {}).get("role") for p in scenario["players"]} - {None}

        assert len(roles) <= 1
        assert all("duty" not in p.get("initial_state", {}) for p in scenario["players"])
        assert "mutually_known_roles" not in scenario
        assert "role_personas" not in scenario

    def test_no_meeting_sns_or_shared_market(self, scenario) -> None:
        """meeting・SNS・共有の市場を宣言しない。全員が同じ場に集まる経路になるため。"""
        assert not scenario.get("meeting", {}).get("enabled", False)
        assert not {"sns", "market", "markets", "market_boards", "merchants"} & scenario.keys()

    def test_no_tool_gathers_everyone_in_one_place(self, scenario, runtime) -> None:
        """プロンプトに並ぶツールに、SNS・市場・会議・投票が無い。どれも離れた相手の存在を知らせる経路になる。"""
        tools = set(runtime.build_full_prompt(_player_id(scenario, "haru"))["tools"])

        assert tools & {"sns_read", "sns_publish", "vote", "report_body", "market_view", "market_list_item"} == set()
        assert "speak" in tools

    def test_death_is_not_announced_to_everyone(self, scenario) -> None:
        """遠くで倒れた人の気配を全員に流さない。流すと、知らない誰かがいると分かる。"""
        assert scenario["death"]["announce_globally"] is False

    def test_persona_intro_and_objective_never_mention_the_other_team(self, scenario) -> None:
        """persona・目的・概要に、相手チームの名前も、別のチームがいることも書かない。"""
        names = _names(scenario)
        public = "\n".join(
            [scenario["metadata"].get("llm_public_intro", ""), scenario["metadata"].get("llm_objective_text", "")]
        )
        assert [n for n in names.values() if n in public] == []
        for player in scenario["players"]:
            own = player["persona_prompt"] + "\n" + player.get("objective", "")
            mine = _team_of(player["id"])
            others = [names[p] for t, v in _TEAMS.items() if t != mine for p in v["players"]]
            assert [n for n in others if n in own] == [], player["id"]
        for text in [public] + [p["persona_prompt"] + p.get("objective", "") for p in scenario["players"]]:
            assert "チーム" not in text
            assert "相手" not in text
