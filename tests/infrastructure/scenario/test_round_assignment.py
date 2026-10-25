"""シナリオの ``round_assignment`` で、回ごとに役と初期配置を割り当てる挙動 (#1514)。"""

from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoader,
    ScenarioLoadError,
)

_PLAYERS = ("p1", "p2", "p3", "p4")


def _spot(spot_id: str) -> dict[str, Any]:
    return {
        "id": spot_id,
        "name": spot_id,
        "description": "d",
        "category": "OTHER",
        "atmosphere": {"lighting": "DIM", "temperature": "NORMAL"},
        "interior": {"objects": []},
    }


def _slots() -> list[dict[str, Any]]:
    return [
        {"spawn_spot": "north", "initial_state": {"role": "north"}},
        {"spawn_spot": "north", "initial_state": {"role": "north"}},
        {"spawn_spot": "south", "initial_state": {"role": "south"}},
        {"spawn_spot": "south", "initial_state": {"role": "south"}},
    ]


def _scenario(round_assignment: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "scenario_format_version": "1.0",
        "metadata": {
            "id": "x",
            "title": "x",
            "description": "x",
            "theme": "x",
            "difficulty": "easy",
            "estimated_ticks": 1,
            "author": "x",
            "tags": [],
        },
        "item_specs": [],
        "environment": {
            "weather": {
                "enabled": False,
                "initial": {"weather_type": "CLEAR", "intensity": 0.0},
                "update_interval_ticks": 100,
                "announce_changes": False,
            },
        },
        "spots": [_spot("village"), _spot("north"), _spot("south")],
        "connections": [],
        "players": [
            {
                "id": pid,
                "name": pid.upper(),
                "spawn_spot": "village",
                "initial_items": [],
                "initial_state": {"lamp_lit": False},
            }
            for pid in _PLAYERS
        ],
        "game_end_conditions": {"win": [], "lose": []},
    }
    if round_assignment is not None:
        raw["round_assignment"] = round_assignment
    return raw


def _groups() -> dict[str, Any]:
    return {"groups": [{"players": list(_PLAYERS), "slots": _slots()}]}


def _load(raw: dict[str, Any], *, seed: int | None = 7, round_number: int = 1):
    return ScenarioLoader().load_from_dict(raw, random_seed=seed, round_number=round_number)


def _roles_and_spots(result) -> dict[str, tuple[str | None, str]]:
    return {
        spawn.string_id: (
            spawn.initial_state.get("role"),
            result.id_mapper.get_str("spot", spawn.spawn_spot_id.value),
        )
        for spawn in result.player_spawns
    }


class TestRoundAssignmentApplied:
    """枠を player に割り当て、spawn_spot と initial_state に書き込む挙動を保証する。"""

    def test_each_player_gets_one_slot(self) -> None:
        """group の player は、枠の数だけの役と配置を 1 つずつ受け取る。"""
        result = _load(_scenario(_groups()))

        assigned = _roles_and_spots(result)
        assert sorted(assigned.values()) == sorted([("north", "north")] * 2 + [("south", "south")] * 2)

    def test_slot_initial_state_is_merged_over_the_player(self) -> None:
        """枠の initial_state は player の initial_state に足され、枠に無いキーは残る。"""
        result = _load(_scenario(_groups()))

        assert all(spawn.initial_state["lamp_lit"] is False for spawn in result.player_spawns)

    def test_player_identity_does_not_move(self) -> None:
        """割り当てても player の id と名前の組は変わらない。"""
        result = _load(_scenario(_groups()))

        assert [(s.string_id, s.name) for s in result.player_spawns] == [(p, p.upper()) for p in _PLAYERS]

    def test_same_seed_and_round_give_the_same_assignment(self) -> None:
        """同じシードと同じ回なら、割り当ては毎回同じになる。"""
        first = _roles_and_spots(_load(_scenario(_groups()), seed=7, round_number=2))
        second = _roles_and_spots(_load(_scenario(_groups()), seed=7, round_number=2))

        assert first == second

    def test_assignment_varies_across_rounds(self) -> None:
        """同じシードでも、回の番号が変われば割り当ては変わりうる (10 回のうち 2 通り以上)。"""
        assignments = {
            tuple(sorted(_roles_and_spots(_load(_scenario(_groups()), seed=7, round_number=n)).items()))
            for n in range(1, 11)
        }

        assert len(assignments) >= 2

    def test_result_records_the_assignment(self) -> None:
        """読み込みの結果に、player ごとの枠の番号と、割り当てたあとの spawn_spot・initial_state が残る。"""
        result = _load(_scenario(_groups()), round_number=3)

        recorded = {a.player_string_id: a for a in result.round_assignments}
        assert set(recorded) == set(_PLAYERS)
        assert sorted(a.slot_index for a in recorded.values()) == [0, 1, 2, 3]
        for spawn in result.player_spawns:
            slot = _slots()[recorded[spawn.string_id].slot_index]
            assert recorded[spawn.string_id].spawn_spot == slot["spawn_spot"]
            assert dict(recorded[spawn.string_id].initial_state) == dict(spawn.initial_state)
            assert _roles_and_spots(result)[spawn.string_id] == (slot["initial_state"]["role"], slot["spawn_spot"])

    def test_assignment_varies_across_seeds(self) -> None:
        """同じ回でも、シードが変われば割り当ては変わりうる (10 通りのシードのうち 2 通り以上)。"""
        assignments = {
            tuple(sorted(_roles_and_spots(_load(_scenario(_groups()), seed=seed, round_number=1)).items()))
            for seed in range(10)
        }

        assert len(assignments) >= 2

    def test_groups_are_shuffled_separately(self) -> None:
        """group ごとに、その group の枠だけを並べ替え、group の番号を記録する。"""
        groups = {
            "groups": [
                {"players": ["p1", "p2"], "slots": _slots()[:2]},
                {"players": ["p3", "p4"], "slots": _slots()[2:]},
            ]
        }

        result = _load(_scenario(groups))

        assert {p: role for p, (role, _) in _roles_and_spots(result).items()} == {
            "p1": "north",
            "p2": "north",
            "p3": "south",
            "p4": "south",
        }
        assert {a.player_string_id: a.group_index for a in result.round_assignments} == {
            "p1": 0,
            "p2": 0,
            "p3": 1,
            "p4": 1,
        }

    def test_slot_without_spawn_spot_keeps_the_declared_spot(self) -> None:
        """枠に spawn_spot が無ければ宣言どおりの場所から始まり、記録にもその場所が残る。"""
        slots = [{"initial_state": {"role": "north"}}, {"initial_state": {"role": "south"}}]

        result = _load(_scenario({"groups": [{"players": ["p1", "p2"], "slots": slots}]}))

        assert {p: spot for p, (_, spot) in _roles_and_spots(result).items()}["p1"] == "village"
        assert {a.player_string_id: a.spawn_spot for a in result.round_assignments} == {
            "p1": "village",
            "p2": "village",
        }

    def test_loading_does_not_change_the_given_dict(self) -> None:
        """渡したシナリオの dict は書き換えず、同じ dict を別の回で読み直せる。"""
        raw = _scenario(_groups())
        before = repr(raw)

        _load(raw, round_number=1)
        _load(raw, round_number=2)

        assert repr(raw) == before

    def test_players_outside_groups_keep_their_declaration(self) -> None:
        """group に入っていない player は、宣言どおりの配置のまま残る。"""
        groups = {"groups": [{"players": ["p1", "p2"], "slots": _slots()[1:3]}]}

        result = _load(_scenario(groups))

        assigned = _roles_and_spots(result)
        assert assigned["p3"] == (None, "village")
        assert assigned["p4"] == (None, "village")

    def test_without_round_assignment_nothing_is_recorded(self) -> None:
        """round_assignment を書かないシナリオは、シード無しでも読め、割り当ての記録は空。"""
        result = _load(_scenario(None), seed=None)

        assert result.round_assignments == ()
        assert {s for s, _ in _roles_and_spots(result).values()} == {None}


class TestRoundAssignmentRejected:
    """書き間違えた round_assignment を、読み込みの時点で止める挙動を保証する。"""

    def test_missing_seed_raises(self) -> None:
        """シードが無いと割り当てを再現できないので止める。"""
        with pytest.raises(ScenarioLoadError, match="SCENARIO_RANDOM_SEED"):
            _load(_scenario(_groups()), seed=None)

    @pytest.mark.parametrize(
        "round_assignment, message",
        [
            pytest.param({"groups": []}, "groups", id="no-groups"),
            pytest.param({"groups": [{"players": ["p1"], "slots": []}]}, "枠", id="slot-count"),
            pytest.param({"groups": [{"players": [], "slots": []}]}, "枠", id="empty-group"),
            pytest.param({"groups": [{"players": ["p1"], "slots": "north"}]}, "枠", id="slots-not-list"),
            pytest.param(
                {"groups": [{"players": [1], "slots": _slots()[:1]}]}, "player id の配列", id="player-not-str"
            ),
            pytest.param(
                {"groups": [{"players": ["p1", "nobody"], "slots": _slots()[:2]}]},
                "知らない player があります: nobody",
                id="unknown-player",
            ),
            pytest.param(
                {"groups": [{"players": ["p1", "p1"], "slots": _slots()[:2]}]},
                "2 度割り当て.*p1",
                id="same-group-twice",
            ),
            pytest.param(
                {
                    "groups": [
                        {"players": ["p1", "p2"], "slots": _slots()[:2]},
                        {"players": ["p2", "p3"], "slots": _slots()[2:]},
                    ]
                },
                "2 度割り当て.*p2",
                id="two-groups",
            ),
            pytest.param(
                {"groups": [{"players": ["p1"], "slots": [{"spawn": "north"}]}]}, "spawn", id="unknown-slot-key"
            ),
            pytest.param({"groups": [{"players": ["p1"], "slots": [{}]}]}, "spawn_spot", id="empty-slot"),
            pytest.param(
                {"groups": [{"players": ["p1"], "slots": [{"spawn_spot": 3}]}]}, "場所の id", id="spawn-spot-not-str"
            ),
            pytest.param(
                {"groups": [{"players": ["p1"], "slots": [{"initial_state": "north"}]}]},
                "initial_state",
                id="state-not-object",
            ),
            pytest.param(
                {"groups": [{"players": ["p1"], "slots": [{"initial_state": {"role": ["a"]}}]}]},
                r"slots\[0\]\.initial_state\.role",
                id="state-value-not-primitive",
            ),
            pytest.param(
                {"groups": [{"players": ["p1"], "slots": _slots()[:1], "order": "rotate"}]},
                "order",
                id="unknown-group-key",
            ),
            pytest.param(
                {"groups": [{"players": ["p1"], "slots": _slots()[:1]}], "mode": "x"}, "mode", id="unknown-top-key"
            ),
            pytest.param([], "object", id="not-object"),
        ],
    )
    def test_malformed_declaration_raises(self, round_assignment: Any, message: str) -> None:
        """書き間違えた宣言は、どの回に当たるかによらず、書き間違えた場所を指して止める。"""
        with pytest.raises(ScenarioLoadError, match=message):
            _load(_scenario(round_assignment))

    def test_duplicated_player_ids_raise(self) -> None:
        """player の id が重複していると、どちらに割り当てるか決まらないので止める。"""
        raw = _scenario(_groups())
        raw["players"][1]["id"] = "p1"

        with pytest.raises(ScenarioLoadError, match="重複"):
            _load(raw)

    @pytest.mark.parametrize("round_number", [0, -1, True])
    def test_round_number_that_is_not_positive_raises(self, round_number: object) -> None:
        """回の番号が正の整数でなければ止める。"""
        with pytest.raises(ScenarioLoadError, match="回の番号"):
            _load(_scenario(_groups()), round_number=round_number)  # type: ignore[arg-type]

    def test_unknown_spawn_spot_in_slot_raises(self) -> None:
        """枠の spawn_spot が無い場所なら、割り当てた後の読み込みで止める。"""
        slots = _slots()
        slots[0]["spawn_spot"] = "nowhere"

        with pytest.raises(Exception, match="nowhere"):
            _load(_scenario({"groups": [{"players": list(_PLAYERS), "slots": slots}]}))
