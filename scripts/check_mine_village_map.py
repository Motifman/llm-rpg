"""廃坑の山村のマップの骨組み (docs/mine_village_map.json) を検算する。

1. spot_map_validator で、閉路、到達性、大事な場所への 2 通りの道、移動時間と距離の整合を見る
2. 水門・閂・支柱で通路が塞がった状態ごとに、各チームの開始地点から大事な場所まで
   行けるか、何 tick かかるかを数える (spot_map_validator は通路の状態を見ないため)
"""

from __future__ import annotations

import heapq
import itertools
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_rpg_world.infrastructure.scenario.spot_map_validator import (
    KeySpotRequirement,
    MapValidationConfig,
    validate_spot_map,
)

MAP_PATH = Path(__file__).resolve().parent.parent / "docs" / "mine_village_map.json"
STARTS = {"北": "north_shaft_head", "南": "south_adit_mouth"}
KEY_SPOTS = ("lift_landing", "machine_room", "company_office")

# 通路を塞ぐもの。値は、その通路が塞がるかを返す関数。
BLOCKERS: dict[str, Callable[[dict[str, Any]], bool]] = {
    "水門A": lambda c: c.get("floods_with") == "gate_a",
    "水門B": lambda c: c.get("floods_with") == "gate_b",
    "水門C": lambda c: c.get("floods_with") == "gate_c",
    "閂": lambda c: c.get("barrable") is True,
    "支柱": lambda c: c.get("fellable") is True,
}


def shortest_ticks(connections: list[dict[str, Any]], start: str) -> dict[str, int]:
    adjacency: dict[str, list[tuple[str, int]]] = {}
    for c in connections:
        adjacency.setdefault(c["from"], []).append((c["to"], c["travel_ticks"]))
        adjacency.setdefault(c["to"], []).append((c["from"], c["travel_ticks"]))
    best = {start: 0}
    queue = [(0, start)]
    while queue:
        ticks, spot = heapq.heappop(queue)
        if ticks > best.get(spot, ticks):
            continue
        for neighbor, cost in adjacency.get(spot, []):
            candidate = ticks + cost
            if candidate < best.get(neighbor, candidate + 1):
                best[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return best


def main() -> int:
    raw = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    names = {s["id"]: s["name"] for s in raw["spots"]}
    vertical = {c["id"] for c in raw["connections"] if c.get("vertical")}

    print("## 1. spot_map_validator")
    for team, start in STARTS.items():
        result = validate_spot_map(
            raw,
            MapValidationConfig(
                start_spot_id=start,
                key_spots=tuple(KeySpotRequirement(s, "error") for s in KEY_SPOTS),
                strict=True,
                distance_to_tick_ratio=1.0,
            ),
        )
        issues = [
            i
            for i in result.errors + result.warnings
            if not (i.code == "TRAVEL_TICKS_DISTANCE_MISMATCH" and i.connection in vertical)
        ]
        print(f"- {team} ({names[start]}) から: ok={result.ok}, 閉路の数={result.metrics['cycle_rank']}")
        for issue in issues:
            print(f"  - [{issue.severity}] {issue.code}: {issue.message}")
        skipped_vertical = sorted(
            i.connection
            for i in result.warnings
            if i.code == "TRAVEL_TICKS_DISTANCE_MISMATCH" and i.connection is not None and i.connection in vertical
        )
        if skipped_vertical:
            print(
                f"  - (竪坑と横坑の距離の食い違いは、地下を横にずらして描いたためなので除いた: {', '.join(skipped_vertical)})"
            )

    print()
    print("## 2. 通路が塞がった状態ごとの、昇降機の乗り場までの tick (行けなければ ×)")
    header = "| 塞がっているもの | " + " | ".join(f"{t}から乗り場 / 機械室 / 事務所" for t in STARTS) + " |"
    print(header)
    print("|---|" + "---|" * len(STARTS))
    for size in range(len(BLOCKERS) + 1):
        for combo in itertools.combinations(BLOCKERS, size):
            open_connections = [c for c in raw["connections"] if not any(BLOCKERS[b](c) for b in combo)]
            cells = []
            for start in STARTS.values():
                best = shortest_ticks(open_connections, start)
                cells.append(" / ".join(str(best[k]) if k in best else "×" for k in KEY_SPOTS))
            print(f"| {'、'.join(combo) or 'なし'} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
