#!/usr/bin/env python3
"""run の trace から、信念とエピソードごとに「頭に載った回数」「根拠に選ばれた回数」「返った材料の数」を並べる (#1484)。

予期の当否は根拠にだけ返る。頭に載った回数に比例して材料が増えているなら、
根拠の選び方が「頭にあったもの」に寄っていて、いつも載るものが強まる悪循環が
残っている。

数え方:

- 頭に載った回数・根拠に選ばれた回数: ``expectation_settlement`` の ``grounds`` の
  うち、根拠が決まった (``judged``) 予期 1 件ごとに数える。縮退して次のターンに
  問い直した予期は、決まったターンだけを数える
- 返った材料の数: ``expectation_material`` の ``result == "appended"`` を、信念は
  ``belief_ids``、エピソードは ``episode_ids`` で数える。エピソードは当たりの回数
  (``hit_count``) と外れの書き添え (``miss_stamp``) を分ける

使い方:
    uv run python scripts/expectation_grounds_report.py var/runs/<run_id> [...]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GroundsCounts:
    in_mind: Counter[tuple[str, str]] = field(default_factory=Counter)
    chosen: Counter[tuple[str, str]] = field(default_factory=Counter)
    material: Counter[tuple[str, str]] = field(default_factory=Counter)
    unjudged: int = 0


def count(events: Iterable[dict[str, Any]]) -> GroundsCounts:
    counts = GroundsCounts()
    for event in events:
        payload = event.get("payload") or {}
        being = payload.get("being_id") or "?"
        if event.get("kind") == "expectation_settlement":
            for entry in payload.get("grounds") or []:
                if not entry["judged"]:
                    counts.unjudged += 1
                    continue
                for kind, ids, chosen in (
                    ("belief", entry["beliefs_in_mind"], entry["beliefs"]),
                    ("episode", entry["episodes_in_mind"], entry["episodes"]),
                ):
                    counts.in_mind.update((being, f"{kind}:{i}") for i in ids)
                    counts.chosen.update((being, f"{kind}:{i}") for i in chosen)
        elif event.get("kind") == "expectation_material" and payload.get("result") == "appended":
            if payload.get("receiver") == "belief_evidence":
                counts.material.update(
                    (being, f"belief:{i}") for i in payload.get("belief_ids") or []
                )
            elif payload.get("receiver") == "recall_credit":
                credit = payload.get("credit")
                counts.material.update(
                    (being, f"episode:{i}:{credit}") for i in payload.get("episode_ids") or []
                )
    return counts


def rows(counts: GroundsCounts) -> list[dict[str, Any]]:
    """頭に載った回数の多い順に、根拠に選ばれた回数と返った材料の数を並べる。"""
    keys = set(counts.in_mind) | set(counts.chosen)
    table = [
        {
            "being_id": being,
            "id": key,
            "in_mind": counts.in_mind[(being, key)],
            "chosen": counts.chosen[(being, key)],
            "material": counts.material[(being, key)],
            "hit_count": counts.material[(being, f"{key}:hit_count")],
            "miss_stamp": counts.material[(being, f"{key}:miss_stamp")],
        }
        for being, key in keys
    ]
    table.sort(key=lambda r: (-r["in_mind"], r["being_id"], r["id"]))
    return table


def _events(run_dir: Path) -> Iterable[dict[str, Any]]:
    with (run_dir / "trace.jsonl").open(encoding="utf-8") as lines:
        for line in lines:
            if line.strip():
                yield json.loads(line)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dirs", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for run_dir in args.run_dirs:
        counts = count(_events(run_dir))
        print(f"# {run_dir}")
        print(f"根拠が決まらなかった予期 (縮退): {counts.unjudged}")
        print("being_id\tid\t頭に載った\t根拠に選ばれた\t材料(信念)\t当たりの回数\t外れの書き添え")
        for r in rows(counts):
            print(
                f"{r['being_id']}\t{r['id']}\t{r['in_mind']}\t{r['chosen']}\t"
                f"{r['material']}\t{r['hit_count']}\t{r['miss_stamp']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
