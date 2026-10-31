"""古い snapshot から読み捨てた記憶の種類の宣言と、仮の名前と一人称が、実験の trace の snapshot_load に残ることを保証する (design_decisions D1469-1、D1469-2)。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import run_scenario_experiment  # noqa: E402


@pytest.mark.parametrize(
    "declared, expected_counts",
    [(None, None), (["memo", "semantic", "semantic"], {"memo": 1, "semantic": 2})],
)
def test_snapshot_load_reports_removed_declarations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    declared: list[str] | None,
    expected_counts: dict[str, int] | None,
) -> None:
    """宣言の残る古い snapshot を読んだ Being だけ、種類ごとの件数を snapshot_load に載せ、記憶本文の件数と分ける。"""
    monkeypatch.setattr(run_scenario_experiment, "_load_dotenv_safe", lambda: None)
    common = ["--profile", "smoke_stub", "--no-html", "--no-progress-jsonl", "--no-stderr-progress"]
    snapshots = tmp_path / "snapshots"
    assert (
        run_scenario_experiment.main([*common, "--out", str(tmp_path / "first"), "--snapshot-save-dir", str(snapshots)])
        == 0
    )
    path = sorted(snapshots.glob("being_*.json"))[0]
    snapshot = json.loads(path.read_text())
    if declared is not None:
        snapshot["declared_memory_kinds"] = declared
    path.write_text(json.dumps(snapshot))

    assert (
        run_scenario_experiment.main(
            [*common, "--out", str(tmp_path / "second"), "--snapshot-load-dir", str(snapshots)]
        )
        == 0
    )
    events = [json.loads(line) for line in (tmp_path / "second" / "trace.jsonl").read_text().splitlines()]
    (loaded,) = [event["payload"] for event in events if event["kind"] == "snapshot_load"]
    expected = [{"being_id": snapshot["being_id_value"], "counts": expected_counts}] if expected_counts else []
    assert loaded["removed_declared_memory_kinds"] == expected
    assert loaded["removed_memory_keys"] == []
    assert loaded["restored_count"] > 1


def test_snapshot_load_reports_dropped_legacy_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """persona の無い古い snapshot から再開すると、仮の名前と一人称を読み捨てて snapshot_load に残し、シナリオの名前で続く (design_decisions D1469-2)。"""
    monkeypatch.setattr(run_scenario_experiment, "_load_dotenv_safe", lambda: None)
    common = ["--profile", "smoke_stub", "--no-html", "--no-progress-jsonl", "--no-stderr-progress"]
    snapshots = tmp_path / "snapshots"
    assert (
        run_scenario_experiment.main([*common, "--out", str(tmp_path / "first"), "--snapshot-save-dir", str(snapshots)])
        == 0
    )
    path = sorted(snapshots.glob("being_*.json"))[0]
    snapshot = json.loads(path.read_text())
    scenario_name = snapshot.pop("persona")["name"]
    snapshot.update(identity_name="agent_1", identity_first_person="わたし")
    path.write_text(json.dumps(snapshot))
    resaved = tmp_path / "resaved"

    assert (
        run_scenario_experiment.main(
            [
                *common,
                "--out",
                str(tmp_path / "second"),
                "--snapshot-load-dir",
                str(snapshots),
                "--snapshot-save-dir",
                str(resaved),
            ]
        )
        == 0
    )
    events = [json.loads(line) for line in (tmp_path / "second" / "trace.jsonl").read_text().splitlines()]
    (loaded,) = [event["payload"] for event in events if event["kind"] == "snapshot_load"]
    assert loaded["removed_legacy_identities"] == [
        {"being_id": snapshot["being_id_value"], "name": "agent_1", "first_person": "わたし"}
    ]
    assert json.loads((resaved / path.name).read_text())["persona"]["name"] == scenario_name
