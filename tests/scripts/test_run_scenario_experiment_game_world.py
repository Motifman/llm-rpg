from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_scenario_experiment import main  # noqa: E402

_SCENARIOS = _REPO_ROOT / "data" / "scenarios"
_MINE_VILLAGE_V2 = _SCENARIOS / "mine_village_v2.yaml"


def _run_end(out: Path) -> dict[str, object]:
    [end] = [e for e in map(json.loads, (out / "trace.jsonl").read_text().splitlines()) if e["kind"] == "run_end"]
    return end["payload"]


def _without_day_night(tmp_path: Path) -> Path:
    shutil.copytree(_SCENARIOS / "common", tmp_path / "common")
    text = _MINE_VILLAGE_V2.read_text(encoding="utf-8")
    start = text.index("  day_night:\n")
    end = start + 5 + re.search(r"\n  [a-z_]+:", text[start + 5 :]).start() + 1  # type: ignore[union-attr]
    scenario = tmp_path / "mine_village_without_day_night.yaml"
    scenario.write_text(text[:start] + "  day_night: null\n" + text[end:], encoding="utf-8")
    return scenario


def _profile(tmp_path: Path, **overrides: object) -> Path:
    profile = json.loads((_REPO_ROOT / "data" / "experiment_profiles" / "smoke_stub_game_world.json").read_text())
    profile.update(overrides)
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    return path


class TestGameWorldSmokeRun:
    """run の入口が、profile の world に game_world と書かれたとき、新しい世界で廃坑の山村 v2 を回すことを保証する。"""

    def test_smoke_profile_plays_the_mine_village_to_the_round_limit(self, tmp_path: Path) -> None:
        """smoke_stub_game_world で 3 tick 回すと、4 人が毎巡りターンを終え (12 ターン)、決めた巡りの数で止まったと run_end に残る。"""
        out = tmp_path / "run"

        code = main(["--profile", "smoke_stub_game_world", "--out", str(out)])

        assert code == 0
        end = _run_end(out)
        assert (end["outcome"], end["last_tick"], end["finished_turns"]) == ("ROUND_LIMIT_REACHED", 3, 12)
        assert end["memory_writing_failures"] == {}
        assert (out / "report.md").exists()

    def test_resolved_config_marks_the_game_world_and_the_scenario_hash(self, tmp_path: Path) -> None:
        """experiment.config.resolved.json に、新しい世界で動いた印 (world=game_world) とシナリオの sha256 が残る。"""
        out = tmp_path / "run"

        main(["--profile", "smoke_stub_game_world", "--out", str(out), "--max-world-ticks", "1"])

        resolved = json.loads((out / "experiment.config.resolved.json").read_text())
        assert resolved["world"] == "game_world"
        assert resolved["scenario_sha256"] == hashlib.sha256(_MINE_VILLAGE_V2.read_bytes()).hexdigest()
        assert resolved["runtime_config"]["wake_waiting_after_rounds"] == 3


class TestGameWorldStopsAtTheEntrance:
    """run の入口が、新しい世界で回せない条件を、世界を開く前に止めて知らせることを保証する。"""

    def test_scenario_without_day_and_night_is_stopped_before_anything_is_written(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """昼夜を宣言していないシナリオを渡すと、昼夜が要ると知らせて終了し、出力の場所に何も作らない。"""
        out = tmp_path / "run"

        with pytest.raises(SystemExit) as stopped:
            main(
                [
                    "--profile",
                    "smoke_stub_game_world",
                    "--scenario",
                    str(_without_day_night(tmp_path)),
                    "--out",
                    str(out),
                ]
            )

        assert stopped.value.code == 2
        assert not out.exists()
        assert "declares no day and night" in capsys.readouterr().err

    def test_key_the_game_world_does_not_read_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """古い世界の鍵 (LLM_IDLE_TIMEOUT_TICKS) を runtime_config に書くと、効かない設定として断り、run を始めない。"""
        profile = _profile(tmp_path, runtime_config={"LLM_CLIENT": "stub", "LLM_IDLE_TIMEOUT_TICKS": 6})

        with pytest.raises(SystemExit) as stopped:
            main(["--experiment-config", str(profile), "--out", str(tmp_path / "run")])

        assert stopped.value.code == 2
        assert "LLM_IDLE_TIMEOUT_TICKS" in capsys.readouterr().err

    def test_snapshot_cannot_be_saved_in_the_game_world_yet(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """新しい世界の profile で snapshot_save を真にすると、まだ保存できないと断る。"""
        profile = _profile(tmp_path, snapshot_save=True)

        with pytest.raises(SystemExit) as stopped:
            main(["--experiment-config", str(profile), "--out", str(tmp_path / "run")])

        assert stopped.value.code == 2
        assert "cannot save or load snapshots" in capsys.readouterr().err

    def test_unknown_world_is_refused(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """world に知らない名前を書くと、古い世界で回さずに断る。"""
        profile = _profile(tmp_path, world="game_wrold")

        with pytest.raises(SystemExit) as stopped:
            main(["--experiment-config", str(profile), "--out", str(tmp_path / "run")])

        assert stopped.value.code == 2
        assert "unknown world" in capsys.readouterr().err
