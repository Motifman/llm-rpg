"""expectation_belief_material_compare が、手の直前に頭にあった信念を、受動想起と状況の項目の想起のどちらの trace からも読む挙動を保証する。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.expectation_belief_material_compare import _in_mind_before_each_action


def _write(path: Path, events: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return path


def test_beliefs_in_mind_are_read_from_either_recall_trace(tmp_path: Path) -> None:
    """semantic_passive_recall なら candidates の ID を、situation_belief_recall なら chosen を、次の手の頭にあった信念にする。"""
    trace = _write(
        tmp_path / "trace.jsonl",
        [
            {"kind": "semantic_passive_recall", "player_id": 1,
             "payload": {"candidates": [{"entry_id": "b-old"}]}},
            {"kind": "action", "player_id": 1, "payload": {}},
            {"kind": "situation_belief_recall", "player_id": 1,
             "payload": {"chosen": ["b-1", "b-2"]}},
            {"kind": "action", "player_id": 1, "payload": {}},
        ],
    )

    rows = _in_mind_before_each_action(trace, 1)

    assert [row.beliefs for row in rows] == [("b-old",), ("b-1", "b-2")]
