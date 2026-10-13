"""記憶だけを持ち越して世界を最初からやり直す入口 (#1514) の通し試験。

smoke_stub (実 LLM を呼ばない) を土台に、``snapshot_load_mode`` だけを
変えた実験設定で回す。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_scenario_experiment import main  # noqa: E402

_COMMON = ["--no-html", "--no-progress-jsonl", "--no-stderr-progress"]


def _config(tmp_path: Path, **overrides: object) -> Path:
    source = json.loads((_REPO_ROOT / "data/experiment_profiles/smoke_stub.json").read_text(encoding="utf-8"))
    source.update(profile=None, snapshot_save=True, **overrides)
    path = tmp_path / f"config_{len(list(tmp_path.glob('config_*')))}.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    return path


def _run(config: Path, out: Path, load_from: Path | None = None, *, ticks: int = 2) -> int:
    load = ["--snapshot-load-dir", str(load_from / "snapshots")] if load_from else []
    return main(["--experiment-config", str(config), "--out", str(out), "--max-world-ticks", str(ticks), *load, *_COMMON])


def _events(run_dir: Path, kind: str) -> list[dict]:
    lines = (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    return [e for e in map(json.loads, lines) if e["kind"] == kind]


def _resolved(run_dir: Path) -> dict:
    return json.loads((run_dir / "experiment.config.resolved.json").read_text(encoding="utf-8"))


class TestReplayRounds:
    """replay の回の番号と、前の回の run が記録に残ることを保証する。"""

    def test_first_round_without_snapshot_is_round_one(self, tmp_path: Path) -> None:
        """snapshot を読まない replay の run は 1 回目として resolved と run_start に残る。"""
        config = _config(tmp_path, snapshot_load_mode="replay")

        assert _run(config, tmp_path / "r1") == 0

        replay = _resolved(tmp_path / "r1")["replay"]
        assert replay["round"] == 1
        assert replay["previous_run_dir"] is None
        (run_start,) = _events(tmp_path / "r1", "run_start")
        assert run_start["payload"]["replay"] == replay

    def test_rounds_count_up_from_the_previous_run(self, tmp_path: Path) -> None:
        """前の回の snapshot を読むたびに回の番号が 1 ずつ増え、前の回の run を指す。"""
        config = _config(tmp_path, snapshot_load_mode="replay")

        assert _run(config, tmp_path / "r1") == 0
        assert _run(config, tmp_path / "r2", load_from=tmp_path / "r1") == 0
        assert _run(config, tmp_path / "r3", load_from=tmp_path / "r2") == 0

        replay = _resolved(tmp_path / "r3")["replay"]
        assert replay["round"] == 3
        assert replay["previous_run_dir"] == str((tmp_path / "r2").resolve())
        assert replay["previous_scenario_sha256"] == replay["scenario_sha256"]

    def test_previous_run_without_resolved_config_stops_before_the_run(self, tmp_path: Path) -> None:
        """前の回の run の resolved が無い snapshot を読もうとすると、run を始める前に止める。"""
        config = _config(tmp_path, snapshot_load_mode="replay")
        (tmp_path / "copied" / "snapshots").mkdir(parents=True)

        with pytest.raises(SystemExit):
            _run(config, tmp_path / "r2", load_from=tmp_path / "copied")

        assert not (tmp_path / "r2" / "trace.jsonl").exists()

    @pytest.mark.parametrize("previous_replay", [{"round": 0}, {"round": "1"}, "round1"])
    def test_previous_round_that_is_not_a_positive_integer_stops_before_the_run(
        self, tmp_path: Path, previous_replay: object
    ) -> None:
        """前の回の resolved の replay.round が正の整数でなければ、run を始める前に止める。"""
        config = _config(tmp_path, snapshot_load_mode="replay")
        (tmp_path / "prev" / "snapshots").mkdir(parents=True)
        (tmp_path / "prev" / "experiment.config.resolved.json").write_text(
            json.dumps({"replay": previous_replay}), encoding="utf-8"
        )

        with pytest.raises(SystemExit):
            _run(config, tmp_path / "r2", load_from=tmp_path / "prev")

        assert not (tmp_path / "r2" / "trace.jsonl").exists()

    def test_unknown_load_mode_stops_before_the_run(self, tmp_path: Path) -> None:
        """snapshot_load_mode に知らない値を書くと、run を始める前に止める。"""
        config = _config(tmp_path, snapshot_load_mode="repaly")

        with pytest.raises(SystemExit):
            _run(config, tmp_path / "r1")

        assert not (tmp_path / "r1" / "trace.jsonl").exists()

    def test_continue_mode_records_no_round(self, tmp_path: Path) -> None:
        """snapshot_load_mode を書かない run は続きからの扱いで、回の番号を持たない。"""
        config = _config(tmp_path)

        assert _run(config, tmp_path / "r1") == 0

        assert _resolved(tmp_path / "r1")["replay"] is None
        assert _resolved(tmp_path / "r1")["snapshot_load_mode"] == "continue"


class TestReplayStartsTheWorldOver:
    """replay の 2 回目が、世界を初期状態から始め、記憶だけを持ち越すことを保証する。"""

    def test_second_round_ignores_world_snapshot_and_carries_memory(self, tmp_path: Path) -> None:
        """2 回目は world.json を読まずに tick 0 から始まり、Being の記憶のターン数は前の回の終わりから続く。"""
        config = _config(tmp_path, snapshot_load_mode="replay")
        assert _run(config, tmp_path / "r1") == 0
        assert (tmp_path / "r1" / "snapshots" / "world.json").exists()

        assert _run(config, tmp_path / "r2", load_from=tmp_path / "r1", ticks=4) == 0

        assert _events(tmp_path / "r2", "world_snapshot_load") == []
        (loaded,) = _events(tmp_path / "r2", "snapshot_load")
        assert loaded["payload"]["restored_being_ids"]
        assert loaded["payload"]["load_mode"] == "replay"
        assert loaded["payload"]["world_snapshot_ignored"] is True
        assert [r["being_id"] for r in loaded["payload"]["world_clock_restarts"]] == loaded["payload"]["restored_being_ids"]
        (saved,) = _events(tmp_path / "r1", "snapshot_save")
        saved_turns = {c["being_id"]: c["memory_turn"] for c in saved["payload"]["memory_turns"]}
        loaded_turns = {c["being_id"]: c["memory_turn"] for c in loaded["payload"]["memory_turns"]}
        assert loaded_turns == saved_turns
        assert any(turn > 0 for turn in loaded_turns.values())
        first_tick = _events(tmp_path / "r2", "tick_start")[0]["tick"]
        assert first_tick == _events(tmp_path / "r1", "tick_start")[0]["tick"]

    def test_continue_mode_resumes_the_world_clock(self, tmp_path: Path) -> None:
        """対照: 続きからの読み込みは world.json を読み、前の回の終わりの tick から始まる。"""
        config = _config(tmp_path)
        assert _run(config, tmp_path / "r1") == 0

        assert _run(config, tmp_path / "r2", load_from=tmp_path / "r1", ticks=4) == 0

        (world_loaded,) = _events(tmp_path / "r2", "world_snapshot_load")
        (loaded,) = _events(tmp_path / "r2", "snapshot_load")
        assert loaded["payload"]["load_mode"] == "continue"
        assert loaded["payload"]["world_snapshot_ignored"] is False
        assert loaded["payload"]["world_clock_restarts"] == []
        assert _events(tmp_path / "r2", "tick_start")[0]["tick"] > _events(tmp_path / "r1", "tick_start")[0]["tick"]
        assert world_loaded["payload"]["world_tick"] > 0


def _scenario_with_round_assignment(tmp_path: Path) -> Path:
    raw = json.loads((_REPO_ROOT / "data/scenarios/survival_island_v3_coop.json").read_text(encoding="utf-8"))
    raw["round_assignment"] = {
        "groups": [{
            "players": [p["id"] for p in raw["players"]],
            "slots": [
                {"spawn_spot": "shipwreck_beach", "initial_state": {"team": "north"}},
                {"spawn_spot": "shipwreck_beach", "initial_state": {"team": "north"}},
                {"spawn_spot": "campsite", "initial_state": {"team": "south"}},
                {"spawn_spot": "campsite", "initial_state": {"team": "south"}},
            ],
        }],
    }
    path = tmp_path / "scenarios" / "island_rounds.json"
    path.parent.mkdir()
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


class TestRoundAssignmentAcrossReplayRounds:
    """replay の回ごとに、シナリオの round_assignment が役と配置を割り当て直すことを保証する。"""

    @staticmethod
    def _assigned(run_dir: Path) -> dict[int, tuple[str, str]]:
        (event,) = _events(run_dir, "round_assignment")
        return {a["player_id"]: (a["initial_state"]["team"], a["spawn_spot"]) for a in event["payload"]["assignments"]}

    @staticmethod
    def _spawned_at(run_dir: Path) -> dict[int, str]:
        return {
            e["player_id"]: e["payload"]["to_spot_id"]
            for e in _events(run_dir, "position_change")
            if e["payload"]["from_spot_id"] is None
        }

    def test_second_round_reassigns_team_and_spawn_with_the_same_people(self, tmp_path: Path) -> None:
        """シード 42 では 1 回目と 2 回目で割り当てが変わり、どちらの回も割り当てた場所から始まり、player の名前は変わらない。"""
        config = _config(tmp_path, snapshot_load_mode="replay", scenario=str(_scenario_with_round_assignment(tmp_path)))

        assert _run(config, tmp_path / "r1") == 0
        assert _run(config, tmp_path / "r2", load_from=tmp_path / "r1") == 0

        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        mapper = ScenarioLoader().load_from_file(tmp_path / "scenarios" / "island_rounds.json", random_seed=42).id_mapper
        spot_ids = {name: str(mapper.get_int("spot", name)) for name in ("shipwreck_beach", "campsite")}
        first, second = self._assigned(tmp_path / "r1"), self._assigned(tmp_path / "r2")
        assert first.keys() == second.keys()
        assert first != second
        for run_dir, assigned in ((tmp_path / "r1", first), (tmp_path / "r2", second)):
            (event,) = _events(run_dir, "round_assignment")
            assert event["payload"]["round"] == _resolved(run_dir)["replay"]["round"]
            assert event["payload"]["seed"] == 42
            spawned = self._spawned_at(run_dir)
            assert {pid: spawned[pid] for pid in assigned} == {pid: spot_ids[spot] for pid, (_, spot) in assigned.items()}
        names = [{a["player_id"]: a["player_name"] for a in _events(d, "round_assignment")[0]["payload"]["assignments"]} for d in (tmp_path / "r1", tmp_path / "r2")]
        assert names[0] == names[1]

    def test_seed_from_the_experiment_config_reaches_the_assignment(self, tmp_path: Path) -> None:
        """実験設定の SCENARIO_RANDOM_SEED (smoke_stub の 42 と割り当てが違う 3) が割り当てに届き、trace の seed もその値になる。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        scenario = _scenario_with_round_assignment(tmp_path)
        source = json.loads((_REPO_ROOT / "data/experiment_profiles/smoke_stub.json").read_text(encoding="utf-8"))
        config = _config(
            tmp_path,
            snapshot_load_mode="replay",
            scenario=str(scenario),
            runtime_config={**source["runtime_config"], "SCENARIO_RANDOM_SEED": 3},
        )

        assert _run(config, tmp_path / "r1") == 0

        (event,) = _events(tmp_path / "r1", "round_assignment")
        assert event["payload"]["seed"] == 3
        expected = ScenarioLoader().load_from_file(scenario, random_seed=3, round_number=1)
        smoke_seed = ScenarioLoader().load_from_file(scenario, random_seed=42, round_number=1)
        assert [a.slot_index for a in expected.round_assignments] != [a.slot_index for a in smoke_seed.round_assignments]
        assert {a["player_name"]: a["slot_index"] for a in event["payload"]["assignments"]} == {
            next(p.name for p in expected.player_spawns if p.string_id == a.player_string_id): a.slot_index
            for a in expected.round_assignments
        }

    def test_same_seed_and_round_reproduce_the_assignment(self, tmp_path: Path) -> None:
        """同じシードの 1 回目を 2 度回すと、割り当ては同じになる (回の番号の配線は 2 回目の試験が見る)。"""
        config = _config(tmp_path, snapshot_load_mode="replay", scenario=str(_scenario_with_round_assignment(tmp_path)))

        assert _run(config, tmp_path / "a") == 0
        assert _run(config, tmp_path / "b") == 0

        assert self._assigned(tmp_path / "a") == self._assigned(tmp_path / "b")

    def test_scenario_without_round_assignment_emits_no_event(self, tmp_path: Path) -> None:
        """round_assignment の無いシナリオでは、割り当ての trace を出さない。"""
        config = _config(tmp_path, snapshot_load_mode="replay")

        assert _run(config, tmp_path / "r1") == 0

        assert _events(tmp_path / "r1", "round_assignment") == []
