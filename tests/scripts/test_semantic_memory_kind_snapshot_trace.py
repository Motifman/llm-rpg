"""旧snapshotから廃止済みの宣言を除去した件数が実験ログに残ることを保証する。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import run_scenario_experiment  # noqa: E402


@pytest.mark.parametrize("removed_count", [0, 2])
def test_snapshot_load_reports_removed_declarations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, removed_count: int
) -> None:
    """semantic宣言があるBeingだけ除去数をsnapshot_loadへ載せ、記憶本文の件数と区別する。"""
    monkeypatch.setattr(run_scenario_experiment, "_load_dotenv_safe", lambda: None)
    common = ["--profile", "smoke_stub", "--no-html", "--no-progress-jsonl", "--no-stderr-progress"]
    snapshots = tmp_path / "snapshots"
    assert (
        run_scenario_experiment.main([*common, "--out", str(tmp_path / "first"), "--snapshot-save-dir", str(snapshots)])
        == 0
    )
    path = sorted(snapshots.glob("being_*.json"))[0]
    snapshot = json.loads(path.read_text())
    snapshot["declared_memory_kinds"] = ["memo", *(["semantic"] * removed_count)]
    path.write_text(json.dumps(snapshot))

    assert (
        run_scenario_experiment.main(
            [*common, "--out", str(tmp_path / "second"), "--snapshot-load-dir", str(snapshots)]
        )
        == 0
    )
    events = [json.loads(line) for line in (tmp_path / "second" / "trace.jsonl").read_text().splitlines()]
    (loaded,) = [event["payload"] for event in events if event["kind"] == "snapshot_load"]
    expected = (
        [{"being_id": snapshot["being_id_value"], "counts": {"semantic": removed_count}}] if removed_count else []
    )
    assert loaded["removed_declared_memory_kinds"] == expected
    assert loaded["removed_memory_keys"] == []
    assert loaded["restored_count"] > 1
