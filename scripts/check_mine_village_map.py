"""廃坑の山村のマップの骨組み (docs/mine_village_map.json) を検算する。

1. spot_map_validator で、閉路、到達性、大事な場所への 2 通りの道、移動時間と距離の整合を見る
2. 水門・閂・支柱で通路が塞がった状態ごとに、各チームの開始地点から大事な場所まで
   行けるか、何 tick かかるかを数える (spot_map_validator は通路の状態を見ないため)
3. 各チームが開始地点から鍵・燃料・発電機・籠を経て脱出するまでの最短の tick を数え、
   実 run の上限に収まるかを見る。収まらなければ 1 を返す
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

# 実 run の上限。profile の max_world_ticks で、シナリオの外にある。
RUN_TICK_LIMIT = 40
# 発電機を動かしてから、昇降機が動くまで温める tick (シナリオの generator_warm)。
WARM_TICKS = 6

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


def win_path_ticks(connections: list[dict[str, Any]]) -> dict[str, int]:
    """2 人が分かれて動く、何も塞がっていない地図での、脱出までの最短の tick。

    操作は 1 回 1 tick (灯す、引き出しを探る、金庫を開ける、缶を取る、注ぐ、発電機を
    動かす、乗り込む、昇降機を動かす)。暗い場所で操作する前には灯す。脱出は昇降機を
    動かした tick のうちに決まる (design_decisions D1618)。
    """

    def d(a: str, b: str) -> int:
        return shortest_ticks(connections, a)[b]

    n, s = STARTS["北"], STARTS["南"]
    office, machine, lift, gas = "company_office", "machine_room", "lift_landing", "gas_chamber"

    def finish(generator_started: int, *ready_at_lift: int) -> int:
        return max(generator_started + WARM_TICKS, *ready_at_lift) + 1

    # 北の 1 人: 持っている缶を機械室で注いで発電機を動かし、乗り場で灯して乗り込む。
    north_generator = d(n, machine) + 3
    north_engineer = north_generator + d(machine, lift) + 2
    # 北のもう 1 人: 乗り場の張り紙で鍵のありかを知り、事務所の引き出しで番号を見つけて戻る。
    north_discover = d(n, lift) + 1 + d(lift, office) + 2 + d(office, lift) + 2
    # 鍵のありかと番号を最初から知っている回 (記憶を持ち越した回)。
    north_knows = d(n, office) + 1 + d(office, lift) + 2
    # 南の 1 人: 番号を知っているので金庫を開けて乗り場へ。もう 1 人: 掘り場の缶を取って発電機を動かす。
    south_key = d(s, office) + 1 + d(office, lift) + 2
    south_generator = d(s, gas) + 2 + d(gas, machine) + 2
    south_engineer = south_generator + d(machine, lift) + 2
    return {
        "北 (乗り場で鍵を知る)": finish(north_generator, north_engineer, north_discover),
        "北 (鍵と番号を知っている)": finish(north_generator, north_engineer, north_knows),
        "南": finish(south_generator, south_engineer, south_key),
    }


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
                distance_to_tick_ratio=2.0,
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

    print()
    print(f"## 3. 脱出までの最短の tick (実 run の上限 {RUN_TICK_LIMIT})")
    over = False
    for path, ticks in win_path_ticks(raw["connections"]).items():
        fits = ticks <= RUN_TICK_LIMIT
        over = over or not fits
        print(f"- {path}: {ticks}{'' if fits else ' (上限を超える)'}")
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
