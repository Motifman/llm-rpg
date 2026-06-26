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
    # PR-C: afterglow 指標。「ぼんやり覚えてる」階層の動きを観測する。
    afterglow_sizes: list[int] = []
    afterglow_slot_evicted = 0
    afterglow_weak_recall = 0
    afterglow_decisions_seen = 0

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
        afterglow = p.get("afterglow")
        if isinstance(afterglow, dict):
            afterglow_decisions_seen += 1
            afterglow_sizes.append(int(afterglow.get("size", 0)))
            for e in afterglow.get("entries") or []:
                src = e.get("source")
                if src == "slot_evicted":
                    afterglow_slot_evicted += 1
                elif src == "weak_recall":
                    afterglow_weak_recall += 1

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
        "afterglow_decisions_seen": afterglow_decisions_seen,
        "afterglow_size_mean": (
            round(statistics.fmean(afterglow_sizes), 2)
            if afterglow_sizes
            else 0
        ),
        "afterglow_size_max": max(afterglow_sizes) if afterglow_sizes else 0,
        "afterglow_slot_evicted_entries_total": afterglow_slot_evicted,
        "afterglow_weak_recall_entries_total": afterglow_weak_recall,
    }


def _format_side_by_side(
    columns: list[tuple[str, dict[str, Any]]],
) -> str:
    """N 個の summary を「指標 | col1 | col2 | … | colN」の表で並べる。

    ``columns`` は ``(label, summary_dict)`` の列。指標キーは最初に
    現れた順で揃え、欠損は「-」で埋める。後方互換のため 2 列入力でも
    そのまま動く。
    """
    keys: list[str] = []
    for _label, summary in columns:
        for k in summary:
            if k not in keys:
                keys.append(k)
    header = "| 指標 | " + " | ".join(label for label, _ in columns) + " |"
    separator = "|---|" + "|".join("---" for _ in columns) + "|"
    lines = [header, separator]
    for k in keys:
        vals = " | ".join(str(s.get(k, "-")) for _, s in columns)
        lines.append(f"| `{k}` | {vals} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="想起スロット ablation 比較 (任意個の run dir を並べる)"
    )
    parser.add_argument(
        "--off", type=Path, help="slot OFF (baseline) の run dir"
    )
    parser.add_argument(
        "--on", type=Path, help="slot ON (afterglow なし) の run dir"
    )
    parser.add_argument(
        "--afterglow",
        type=Path,
        help="slot ON + afterglow ON の run dir (任意)",
    )
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        metavar="LABEL=DIR",
        help="任意ラベル付きの run dir を追加。複数回指定可 (例: --run=control=var/runs/foo)",
    )
    args = parser.parse_args()

    columns: list[tuple[str, dict[str, Any]]] = []

    def _add(label: str, run_dir: Path) -> None:
        trace = run_dir / "trace.jsonl"
        if not trace.exists():
            raise SystemExit(f"trace.jsonl not found: {trace}")
        columns.append((label, _summarize(_load_episodic_recall_events(trace))))

    if args.off:
        _add("slot OFF", args.off)
    if args.on:
        _add("slot ON", args.on)
    if args.afterglow:
        _add("slot ON + afterglow", args.afterglow)
    for spec in args.run:
        if "=" not in spec:
            raise SystemExit(f"--run must be LABEL=DIR (got {spec})")
        label, raw = spec.split("=", 1)
        _add(label.strip(), Path(raw.strip()))

    if not columns:
        raise SystemExit("少なくとも 1 つの run dir を指定してください")

    print("# 想起スロット ablation 比較\n")
    for label, _ in columns:
        print(f"- {label}")
    print()
    print(_format_side_by_side(columns))


if __name__ == "__main__":
    main()
