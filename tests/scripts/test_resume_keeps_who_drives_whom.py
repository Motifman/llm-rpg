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


def _as_old_being_snapshots(snapshot_dir: Path) -> None:
    """Being の snapshot を、居場所を世界とプレイヤーの番号で持っていた古い形に書き換える。"""
    for path in snapshot_dir.glob("being_w1_p*.json"):
        data = json.loads(path.read_text())
        data.pop("attachment_environment_id")
        data.pop("attachment_environment_name")
        data.update(attachment_world_id=1, attachment_player_id=int(path.stem.removeprefix("being_w1_p")))
        path.write_text(json.dumps(data, ensure_ascii=False))


@pytest.mark.parametrize(
    ("drop_table", "old_beings", "source"),
    [(False, False, "world_snapshot"), (True, True, "being_snapshots"), (True, False, "startup")],
)
def test_resumed_run_keeps_the_same_beings_on_the_same_players(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drop_table: bool, old_beings: bool, source: str
) -> None:
    """再開した run は、保存した対応表と同じ組で続く。

    対応表の欄を消した古い世界の snapshot でも、古い Being の snapshot の番号から同じ組を作り直す。番号も無ければ、
    起動時に用意した対応表 (Being の ID はプレイヤーから決まる) で同じ組になる。
    """
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
    if old_beings:
        _as_old_being_snapshots(saved)

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
