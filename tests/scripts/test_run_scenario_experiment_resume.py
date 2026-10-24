"""snapshot から続きを再開する入口と、replay を外したあとの実験設定の通し試験。

smoke_stub (実 LLM を呼ばない) を土台にした実験設定で回す。記憶だけを持ち越して
世界を最初からやり直す replay (#1514) は外した (design_decisions D1514 の「その後」)。
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


class TestReplayIsGone:
    """replay を外したあと、実験設定と記録に replay の口が残らないことを保証する。"""

    @pytest.mark.parametrize("mode", ["replay", "continue"])
    def test_snapshot_load_mode_in_the_config_stops_before_the_run(self, tmp_path: Path, mode: str) -> None:
        """実験設定に snapshot_load_mode を書くと、値に関わらず黙って無視せず、run を始める前に止める。"""
        config = _config(tmp_path, snapshot_load_mode=mode)

        with pytest.raises(SystemExit):
            _run(config, tmp_path / "r1")

        assert not (tmp_path / "r1").exists()

    def test_resolved_and_run_start_have_no_replay_fields(self, tmp_path: Path) -> None:
        """resolved と run_start に、replay の回の番号と読み方の欄を残さない。"""
        config = _config(tmp_path)

        assert _run(config, tmp_path / "r1") == 0

        resolved = _resolved(tmp_path / "r1")
        assert "replay" not in resolved
        assert "snapshot_load_mode" not in resolved
        (run_start,) = _events(tmp_path / "r1", "run_start")
        assert "replay" not in run_start["payload"]


class TestResumeContinuesTheWorld:
    """snapshot からの再開が、世界も記憶も続きから始めることを保証する。"""

    def test_resume_loads_the_world_and_the_memory(self, tmp_path: Path) -> None:
        """再開は world.json を読み、前の回の終わりの tick から始まり、Being の記憶のターン数も続く。snapshot_load に replay の欄は無い。"""
        config = _config(tmp_path)
        assert _run(config, tmp_path / "r1") == 0

        assert _run(config, tmp_path / "r2", load_from=tmp_path / "r1", ticks=4) == 0

        (world_loaded,) = _events(tmp_path / "r2", "world_snapshot_load")
        (loaded,) = _events(tmp_path / "r2", "snapshot_load")
        assert "load_mode" not in loaded["payload"]
        assert "world_snapshot_ignored" not in loaded["payload"]
        assert loaded["payload"]["removed_memory_keys"] == []
        (saved,) = _events(tmp_path / "r1", "snapshot_save")
        saved_turns = {c["being_id"]: c["memory_turn"] for c in saved["payload"]["memory_turns"]}
        loaded_turns = {c["being_id"]: c["memory_turn"] for c in loaded["payload"]["memory_turns"]}
        assert loaded_turns == saved_turns
        assert _events(tmp_path / "r2", "tick_start")[0]["tick"] > _events(tmp_path / "r1", "tick_start")[0]["tick"]
        assert world_loaded["payload"]["world_tick"] > 0


def _add_old_memo_to_one_snapshot(snapshot_dir: Path) -> str:
    """snapshot の 1 本に、古いメモの欄を書き足す。書き足した Being の ID を返す。"""
    path = sorted(p for p in snapshot_dir.glob("*.json") if p.name != "world.json")[0]
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    payload = json.loads(snapshot["memory_payload_json"])
    payload["memo"] = [
        {"id": "m1", "content": "井戸は北", "added_at_tick": 90},
        {"id": "m2", "content": "鍵を探す", "added_at_tick": 91},
    ]
    snapshot["memory_payload_json"] = json.dumps(payload, ensure_ascii=False)
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    return snapshot["being_id_value"]


class TestOldSnapshotWithRemovedMemoryKeys:
    """消した部品の欄を持つ古い snapshot も読み込め、捨てた件数が trace に残ることを保証する。"""

    def test_old_memo_is_dropped_and_counted_in_the_trace(self, tmp_path: Path) -> None:
        """古いメモを持つ snapshot から再開すると、run は止まらず、snapshot_load の removed_memory_keys にその Being の件数だけが載る。"""
        config = _config(tmp_path)
        assert _run(config, tmp_path / "r1") == 0
        being_id = _add_old_memo_to_one_snapshot(tmp_path / "r1" / "snapshots")

        assert _run(config, tmp_path / "r2", load_from=tmp_path / "r1") == 0

        (loaded,) = _events(tmp_path / "r2", "snapshot_load")
        assert loaded["payload"]["removed_memory_keys"] == [{"being_id": being_id, "counts": {"memo": 2}}]


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


class TestRoundAssignmentFromTheSeed:
    """シナリオの round_assignment が、実験設定のシードで役と配置を割り当てることを保証する。"""

    @staticmethod
    def _assigned(run_dir: Path) -> dict[int, tuple[str, str]]:
        (event,) = _events(run_dir, "round_assignment")
        return {a["player_id"]: (a["initial_state"]["team"], a["spawn_spot"]) for a in event["payload"]["assignments"]}

    def test_seed_from_the_experiment_config_reaches_the_assignment(self, tmp_path: Path) -> None:
        """実験設定の SCENARIO_RANDOM_SEED (smoke_stub の 42 と割り当てが違う 3) が割り当てに届き、trace の seed もその値になり、回は 1 回目のまま。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        scenario = _scenario_with_round_assignment(tmp_path)
        source = json.loads((_REPO_ROOT / "data/experiment_profiles/smoke_stub.json").read_text(encoding="utf-8"))
        config = _config(
            tmp_path,
            scenario=str(scenario),
            runtime_config={**source["runtime_config"], "SCENARIO_RANDOM_SEED": 3},
        )

        assert _run(config, tmp_path / "r1") == 0

        (event,) = _events(tmp_path / "r1", "round_assignment")
        assert event["payload"]["seed"] == 3
        assert event["payload"]["round"] == 1
        expected = ScenarioLoader().load_from_file(scenario, random_seed=3, round_number=1)
        smoke_seed = ScenarioLoader().load_from_file(scenario, random_seed=42, round_number=1)
        assert [a.slot_index for a in expected.round_assignments] != [a.slot_index for a in smoke_seed.round_assignments]
        assert {a["player_name"]: a["slot_index"] for a in event["payload"]["assignments"]} == {
            next(p.name for p in expected.player_spawns if p.string_id == a.player_string_id): a.slot_index
            for a in expected.round_assignments
        }

    def test_same_seed_reproduces_the_assignment(self, tmp_path: Path) -> None:
        """同じシードで 2 度回すと、割り当ては同じになる。"""
        config = _config(tmp_path, scenario=str(_scenario_with_round_assignment(tmp_path)))

        assert _run(config, tmp_path / "a") == 0
        assert _run(config, tmp_path / "b") == 0

        assert self._assigned(tmp_path / "a") == self._assigned(tmp_path / "b")

    def test_scenario_without_round_assignment_emits_no_event(self, tmp_path: Path) -> None:
        """round_assignment の無いシナリオでは、割り当ての trace を出さない。"""
        config = _config(tmp_path)

        assert _run(config, tmp_path / "r1") == 0

        assert _events(tmp_path / "r1", "round_assignment") == []
