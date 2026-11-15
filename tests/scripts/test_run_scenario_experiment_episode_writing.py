"""実 LLM を呼ばない run で、Being の短期記憶の範囲が埋まったときと環境を離れるときに書いたエピソードが、trace と snapshot に残ることを保証する (#1626、design_decisions D1824-21)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


def _events(trace_path: Path, kind: str) -> list[dict]:
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    return [e for e in map(json.loads, lines) if e["kind"] == kind]


def test_stub_run_writes_episodes_on_filled_range_and_on_leaving_before_the_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """スタブの run で、範囲が埋まったときと環境を離れるときの両方でエピソードを書き、書いたエピソードの数だけ snapshot に入る。今の短期記憶を畳むときには書かない。

    本番の手数 (20 手で埋まる) のままだと smoke_stub で 84 tick 回すことになり遅いので、
    短期記憶のモジュールの手数の定数を 2 / 2 / 6 に下げて 12 tick で埋める。
    畳む手数を埋まる手数と同じにして、離れるときの 3 手目で範囲が埋まり直さないようにする。
    埋まり直すと、範囲が埋まったときと離れるときのエピソードが同じターンになり、どちらから書かれたか区別できない。
    そのため、両者のターンが重ならないことも確かめる。
    差し替えが効かなくなったら範囲が埋まらず、range_filled から書いたエピソードの assert で落ちる。
    """
    from scripts.run_scenario_experiment import main

    import ai_rpg_world.being.domain.short_term_memory as short_term_memory

    monkeypatch.setattr(short_term_memory, "RECENT_TURNS", 2)
    monkeypatch.setattr(short_term_memory, "FOLD_TURNS", 2)
    monkeypatch.setattr(short_term_memory, "FORCED_FOLD_TURNS", 6)

    config = json.loads((_REPO / "data/experiment_profiles/smoke_stub.json").read_text(encoding="utf-8"))
    config["profile"] = "episode_writing_stub"
    # このシナリオの 4 人は 4 tick に 1 回ずつ手番が回る。12 tick で 1 人 3 手になり、2 手目で埋まる。
    config["max_world_ticks"] = 12
    config_path = tmp_path / "experiment.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    snapshots = tmp_path / "snapshots"

    rc = main(
        [
            "--experiment-config",
            str(config_path),
            "--out",
            str(tmp_path / "run"),
            "--snapshot-save-dir",
            str(snapshots),
            "--no-html",
            "--no-progress-jsonl",
            "--no-stderr-progress",
        ]
    )

    assert rc == 0
    trace = tmp_path / "run" / "trace.jsonl"
    writes = _events(trace, "episode_writing")
    triggers = {w["payload"]["trigger"] for w in writes if w["payload"]["outcome"] == "written"}
    assert triggers == {"leaving"}
    filled = {
        (e["payload"]["being_id"], e["payload"]["turn"]) for e in _events(trace, "being_short_term_memory_range_filled")
    }
    leaving = {
        (w["payload"]["being_id"], w["payload"]["written_turn"])
        for w in writes
        if w["payload"]["trigger"] == "leaving" and w["payload"]["outcome"] == "written"
    }
    assert not filled & leaving
    episodes = _events(trace, "being_episode_written")
    from_filled = [e for e in episodes if (e["payload"]["being_id"], e["payload"]["written_turn"]) in filled]
    assert filled and from_filled
    written = len(episodes)
    saved = sum(
        path.read_text(encoding="utf-8").count('\\"handle\\": \\"ep_') for path in snapshots.glob("being_*.json")
    )
    assert written > 0
    assert saved == written
