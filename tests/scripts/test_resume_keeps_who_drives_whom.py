"""snapshot から再開しても、同じプレイヤーを同じ Being が動かすことを、実験の入口から保証する (#1928、design_decisions D1928)。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import run_scenario_experiment  # noqa: E402

_COMMON = ["--profile", "smoke_stub", "--no-html", "--no-progress-jsonl", "--no-stderr-progress"]


def _pairs(snapshot_dir: Path) -> list[dict]:
    return json.loads((snapshot_dir / "world.json").read_text())["subsystems"]["player_beings"]["pairs"]


@pytest.mark.parametrize(("drop_table", "source"), [(False, "world_snapshot"), (True, "being_snapshots")])
def test_resumed_run_keeps_the_same_beings_on_the_same_players(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drop_table: bool, source: str
) -> None:
    """再開した run は、保存した対応表と同じ組で続く。対応表の欄を消した古い形でも、Being の snapshot の番号から同じ組を作り直す。"""
    monkeypatch.setattr(run_scenario_experiment, "_load_dotenv_safe", lambda: None)
    saved, resaved = tmp_path / "saved", tmp_path / "resaved"
    assert (
        run_scenario_experiment.main([*_COMMON, "--out", str(tmp_path / "first"), "--snapshot-save-dir", str(saved)])
        == 0
    )
    original = _pairs(saved)
    if drop_table:
        world = json.loads((saved / "world.json").read_text())
        del world["subsystems"]["player_beings"]
        (saved / "world.json").write_text(json.dumps(world))

    assert (
        run_scenario_experiment.main(
            [
                *_COMMON,
                "--out",
                str(tmp_path / "second"),
                "--snapshot-load-dir",
                str(saved),
                "--snapshot-save-dir",
                str(resaved),
            ]
        )
        == 0
    )

    events = [json.loads(line) for line in (tmp_path / "second" / "trace.jsonl").read_text().splitlines()]
    (loaded,) = [event["payload"] for event in events if event["kind"] == "snapshot_load"]
    assert loaded["player_beings_source"] == source
    assert len(original) > 1
    assert _pairs(resaved) == original
