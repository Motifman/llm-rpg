"""想起スロット ablation 比較スクリプト。

2 つの実験 run の trace.jsonl を読み、想起スロットの効果を「測れる量」に
変換して並べる。Issue #526 段階 3 の検証で、PR #580 (slot 基盤) と
PR #583 (PR-A: 希少資源化) の合算効果を実 LLM run で確認するために使う。

# 指標

| 指標 | 何を見るか |
|---|---|
| recall_count_per_tick | 1 tick の recall section に乗ったエピソード件数の分布 |
| recall_chars_per_tick | recall section の文字数 (= prompt 圧 / cache 同一性の代理指標) |
| max_consecutive_same | 同じ episode 集合が何 tick 連続で recall されたか (= 慣化の効き) |
| jaccard_avg | 隣り合う tick の recall 集合の Jaccard 平均 (= 1.0 に近いほど安定) |
| slot_decision_summary | retained / inserted / evicted の合計 (slot ON 時のみ) |

# 使い方

```
uv run python scripts/compare_slot_ablation.py \\
    --off var/runs/ablation_slot_off \\
    --on  var/runs/ablation_slot_on
```
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


def _load_episodic_recall_events(trace_path: Path) -> list[dict[str, Any]]:
    """trace.jsonl から episodic_recall イベントだけ抜き出す。

    1 つの player の 1 tick につき複数の player が動くケースもあるため、
    player_id を付けたまま返す (後段で必要なら group_by する)。
    """
    events: list[dict[str, Any]] = []
    with trace_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("kind") == "episodic_recall":
                events.append(d)
    return events


def _summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    """recall events を測定可能な数値に落とす。"""
    if not events:
        return {"ticks_with_recall": 0}

    candidate_counts: list[int] = []
    chars_totals: list[int] = []
    candidate_id_sets: list[frozenset[str]] = []
    retained_total = 0
    inserted_total = 0
    evicted_total = 0
    slot_decisions_seen = 0

    for d in events:
        p = d.get("payload", {})
        candidate_counts.append(int(p.get("candidate_count", 0)))
        chars_totals.append(int(p.get("recall_text_chars_total", 0)))
        ids = frozenset(
            c.get("episode_id")
            for c in p.get("candidates", [])
            if c.get("episode_id")
        )
        candidate_id_sets.append(ids)
        slot = p.get("recall_slot")
        if isinstance(slot, dict):
            slot_decisions_seen += 1
            retained_total += len(slot.get("retained") or [])
            inserted_total += len(slot.get("inserted") or [])
            evicted_total += len(slot.get("evicted_ids") or [])

    # 連続して同じ recall 集合が出た回数の最大
    max_consec = 1
    cur = 1
    for i in range(1, len(candidate_id_sets)):
        if candidate_id_sets[i] and candidate_id_sets[i] == candidate_id_sets[i - 1]:
            cur += 1
            max_consec = max(max_consec, cur)
        else:
            cur = 1

    # 隣接 tick の Jaccard 平均 (1.0 に近いほど安定)
    jaccards: list[float] = []
    for i in range(1, len(candidate_id_sets)):
        a, b = candidate_id_sets[i - 1], candidate_id_sets[i]
        if not a and not b:
            continue
        union = a | b
        if not union:
            continue
        jaccards.append(len(a & b) / len(union))

    return {
        "ticks_with_recall": len(events),
        "candidate_count_distribution": dict(Counter(candidate_counts)),
        "candidate_count_mean": round(statistics.fmean(candidate_counts), 2)
        if candidate_counts
        else 0,
        "recall_chars_mean": round(statistics.fmean(chars_totals), 1)
        if chars_totals
        else 0,
        "recall_chars_max": max(chars_totals) if chars_totals else 0,
        "max_consecutive_same_recall_set": max_consec,
        "jaccard_avg_adjacent_ticks": round(statistics.fmean(jaccards), 3)
        if jaccards
        else None,
        "slot_decisions_seen": slot_decisions_seen,
        "slot_retained_total": retained_total,
        "slot_inserted_total": inserted_total,
        "slot_evicted_total": evicted_total,
    }


def _format_side_by_side(a: dict[str, Any], b: dict[str, Any]) -> str:
    """2 つの summary を「指標 | OFF | ON | 差」の表で並べる。"""
    keys: list[str] = []
    for k in a:
        if k not in keys:
            keys.append(k)
    for k in b:
        if k not in keys:
            keys.append(k)
    lines = ["| 指標 | slot OFF | slot ON |", "|---|---|---|"]
    for k in keys:
        va, vb = a.get(k, "-"), b.get(k, "-")
        lines.append(f"| `{k}` | {va} | {vb} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="想起スロット ablation 比較 (slot OFF vs slot ON)"
    )
    parser.add_argument("--off", required=True, type=Path, help="slot OFF の run dir")
    parser.add_argument("--on", required=True, type=Path, help="slot ON の run dir")
    args = parser.parse_args()

    off_trace = args.off / "trace.jsonl"
    on_trace = args.on / "trace.jsonl"
    if not off_trace.exists():
        raise SystemExit(f"trace.jsonl not found: {off_trace}")
    if not on_trace.exists():
        raise SystemExit(f"trace.jsonl not found: {on_trace}")

    off_summary = _summarize(_load_episodic_recall_events(off_trace))
    on_summary = _summarize(_load_episodic_recall_events(on_trace))

    print(f"# 想起スロット ablation 比較\n")
    print(f"- slot OFF dir: `{args.off}`")
    print(f"- slot ON  dir: `{args.on}`\n")
    print(_format_side_by_side(off_summary, on_summary))


if __name__ == "__main__":
    main()
