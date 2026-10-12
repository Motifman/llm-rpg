"""実 LLM を呼ばない run で書き起こしを有効にすると、畳むときと環境を離れるときに書いたエピソードが trace と snapshot に残ることを保証する (#1626)。"""

from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def _events(trace_path: Path, kind: str) -> list[dict]:
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    return [e for e in map(json.loads, lines) if e["kind"] == kind]


def test_stub_run_writes_episodes_on_compaction_and_on_leaving_before_the_snapshot(tmp_path: Path) -> None:
    """スタブの run で、畳むときと環境を離れるときの両方で書き起こしが trace に残り、書いたエピソードの数だけ snapshot に入る。"""
    from scripts.run_scenario_experiment import main

    config = json.loads((_REPO / "data/experiment_profiles/smoke_stub.json").read_text(encoding="utf-8"))
    config["profile"] = "episode_writing_stub"
    config["max_world_ticks"] = 12
    config["runtime_config"].update(
        {
            "SHORT_TERM_MEMORY_TURN_CAP": 2,
            "SHORT_TERM_MEMORY_TURN_COMPACT_COUNT": 1,
        }
    )
    config_path = tmp_path / "experiment.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    snapshots = tmp_path / "snapshots"

    rc = main(
        [
            "--experiment-config", str(config_path),
            "--out", str(tmp_path / "run"),
            "--snapshot-save-dir", str(snapshots),
            "--no-html", "--no-progress-jsonl", "--no-stderr-progress",
        ]
    )

    assert rc == 0
    writes = _events(tmp_path / "run" / "trace.jsonl", "episode_writing")
    triggers = {w["payload"]["trigger"] for w in writes if w["payload"]["outcome"] == "written"}
    assert triggers == {"compaction", "leaving"}
    written = sum(w["payload"]["episode_count"] for w in writes if w["payload"]["outcome"] == "written")
    saved = sum(
        path.read_text(encoding="utf-8").count('\\"handle\\": \\"ep_')
        for path in snapshots.glob("being_*.json")
    )
    assert written > 0
    assert saved == written
