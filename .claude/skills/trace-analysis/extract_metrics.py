#!/usr/bin/env python3
"""llm-rpg trace の共通指標を抽出する (trace-analysis SKILL の Step 1)。

入力:
    extract_metrics.py <run_dir> [baseline_dir]

run_dir / baseline_dir はそれぞれ ``trace.jsonl`` を含む dir。

出力 (stdout に JSON):
    {
        "run_dir": "...",
        "baseline_dir": "..." or null,
        "current": { ... metrics ... },
        "baseline": { ... metrics ... } or null,
        "comparison": [ {label, current, baseline}, ... ] or null
    }

設計方針:
- 解析は **trace.jsonl だけで完結**。scenario / config 等は参照しない (再現性)。
- 数値だけでなく **判定材料となる具体例 (loop_guard 詳細 / 失敗 5 件抜粋など) も
  payload に含める**。サブエージェント側が再 grep しないで済むようにする。
- 出力サイズは制限しない (= JSON は parser 側で読む前提)。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def _load_events(run_dir: Path) -> list[dict]:
    path = run_dir / "trace.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"trace.jsonl not found: {path}")
    out: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * p))
    return sorted_values[idx]


def _per_tick_wall_times(events: list[dict]) -> list[tuple[int, float]]:
    """tick_start の timestamp 差分から per-tick 実時間 (s) を抽出。

    戻り値: [(tick, wall_seconds), ...] tick の昇順。
    """
    ticks: list[tuple[int, datetime]] = []
    for e in events:
        if e.get("kind") == "tick_start":
            try:
                ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                ticks.append((e["tick"], ts))
            except Exception:
                continue
    ticks.sort(key=lambda x: x[0])
    deltas: list[tuple[int, float]] = []
    for i in range(len(ticks) - 1):
        dt = (ticks[i + 1][1] - ticks[i][1]).total_seconds()
        deltas.append((ticks[i + 1][0], dt))
    return deltas


def _bucket_20(values: list[tuple[int, float]]) -> list[dict]:
    """tick 値で 20 区切りの bucket に集約。"""
    buckets: dict[int, list[float]] = defaultdict(list)
    for t, v in values:
        buckets[t // 20].append(v)
    out: list[dict] = []
    for b in sorted(buckets):
        vs = buckets[b]
        if not vs:
            continue
        out.append({
            "tick_range": [b * 20, b * 20 + 19],
            "n": len(vs),
            "mean": sum(vs) / len(vs),
            "max": max(vs),
        })
    return out


def _extract_summary(events: list[dict]) -> dict[str, Any]:
    """LLM call / token / cost / 失敗率 / 各種カウントの 1 行サマリ。"""
    llm = [e for e in events if e.get("kind") == "llm_call"]
    latencies = sorted(
        e["payload"]["wall_latency_ms"] / 1000.0
        for e in llm if "wall_latency_ms" in e.get("payload", {})
    )
    prompt_tok = sum(e["payload"].get("prompt_tokens", 0) for e in llm)
    cached_tok = sum(e["payload"].get("cached_tokens", 0) for e in llm)
    comp_tok = sum(e["payload"].get("completion_tokens", 0) for e in llm)
    cost = sum(e["payload"].get("cost_usd", 0) for e in llm)

    total_action = sum(1 for e in events if e.get("kind") == "action_result")
    fail = sum(
        1 for e in events
        if e.get("kind") == "action_result"
        and not e.get("payload", {}).get("success", True)
    )

    counts_by_kind = Counter(e.get("kind") for e in events)

    return {
        "llm_calls": len(llm),
        "latency_p50_s": _percentile(latencies, 0.50),
        "latency_p90_s": _percentile(latencies, 0.90),
        "latency_p99_s": _percentile(latencies, 0.99),
        "latency_max_s": latencies[-1] if latencies else 0.0,
        "prompt_tokens_total": prompt_tok,
        "cached_tokens_total": cached_tok,
        "completion_tokens_total": comp_tok,
        "cache_hit_ratio": (cached_tok / prompt_tok) if prompt_tok else 0.0,
        "cost_usd_total": cost,
        "action_total": total_action,
        "action_fail": fail,
        "action_fail_rate": (fail / total_action) if total_action else 0.0,
        "memo_add": counts_by_kind.get("memo_add", 0),
        "memo_done": counts_by_kind.get("memo_done", 0),
        "episodic_chunk_written": counts_by_kind.get("episodic_chunk_written", 0),
        "episodic_subjective_filled": counts_by_kind.get("episodic_subjective_filled", 0),
        "short_term_summary": counts_by_kind.get("short_term_summary_generated", 0),
        "short_term_long_summary": counts_by_kind.get("short_term_long_summary_generated", 0),
        "loop_guard_warning": counts_by_kind.get("loop_guard_warning", 0),
        "observation": counts_by_kind.get("observation", 0),
    }


def _extract_per_player(events: list[dict]) -> dict[str, Any]:
    """per-player tool histogram と action 数。"""
    per_tool: dict[int, Counter] = defaultdict(Counter)
    per_llm: Counter = Counter()
    per_fail: dict[int, Counter] = defaultdict(Counter)

    prev_action: dict | None = None
    for e in events:
        k = e.get("kind")
        if k == "llm_call":
            per_llm[e.get("player_id")] += 1
        elif k == "action":
            prev_action = e
            per_tool[e.get("player_id", -1)][e["payload"].get("tool", "?")] += 1
        elif k == "action_result" and prev_action is not None:
            if not e.get("payload", {}).get("success", True):
                ec = e.get("payload", {}).get("error_code", "?")
                per_fail[prev_action.get("player_id", -1)][ec] += 1

    out: dict[str, Any] = {}
    all_pids = set(per_llm.keys()) | set(per_tool.keys()) | set(per_fail.keys())
    for pid in sorted(p for p in all_pids if p is not None):
        out[f"P{pid}"] = {
            "llm_calls": per_llm.get(pid, 0),
            "tool_histogram": dict(per_tool.get(pid, Counter()).most_common()),
            "error_code_distribution": dict(per_fail.get(pid, Counter())),
        }
    return out


def _extract_per_tool(events: list[dict]) -> list[dict]:
    """tool 別 成功/失敗/error_code breakdown。"""
    succ: Counter = Counter()
    fail: Counter = Counter()
    errs: dict[str, Counter] = defaultdict(Counter)
    for e in events:
        if e.get("kind") != "action_result":
            continue
        tool = e.get("payload", {}).get("tool", "?")
        if e.get("payload", {}).get("success", True):
            succ[tool] += 1
        else:
            fail[tool] += 1
            ec = e.get("payload", {}).get("error_code", "?")
            errs[tool][ec] += 1

    out: list[dict] = []
    for tool in sorted(set(succ.keys()) | set(fail.keys()), key=lambda x: -(succ[x] + fail[x])):
        total = succ[tool] + fail[tool]
        out.append({
            "tool": tool,
            "total": total,
            "success": succ[tool],
            "fail": fail[tool],
            "fail_rate": fail[tool] / total if total else 0.0,
            "error_codes": dict(errs[tool]),
        })
    return out


def _extract_cache_timeseries(events: list[dict]) -> list[dict]:
    """20 tick 毎の cache hit 率推移。"""
    buckets: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # [cached, prompt]
    for e in events:
        if e.get("kind") != "llm_call":
            continue
        p = e.get("payload", {})
        b = e.get("tick", 0) // 20
        buckets[b][0] += p.get("cached_tokens", 0)
        buckets[b][1] += p.get("prompt_tokens", 0)
    out: list[dict] = []
    for b in sorted(buckets):
        c, pt = buckets[b]
        out.append({
            "tick_range": [b * 20, b * 20 + 19],
            "cached_tokens": c,
            "prompt_tokens": pt,
            "cache_hit_ratio": c / pt if pt else 0.0,
        })
    return out


def _extract_loop_guard(events: list[dict]) -> list[dict]:
    """loop_guard_warning の生 payload を返す (= 何 tick で誰が何で詰まったか)。"""
    return [
        {
            "tick": e.get("tick"),
            "player_id": e.get("player_id"),
            "payload": e.get("payload", {}),
        }
        for e in events
        if e.get("kind") == "loop_guard_warning"
    ]


def _extract_fail_examples(events: list[dict], n: int = 10) -> list[dict]:
    """失敗 action の先頭 n 件を、引数と error 込みで返す。"""
    out: list[dict] = []
    prev_action: dict | None = None
    for e in events:
        if e.get("kind") == "action":
            prev_action = e
        elif e.get("kind") == "action_result" and prev_action is not None:
            if not e.get("payload", {}).get("success", True):
                out.append({
                    "tick": prev_action.get("tick"),
                    "player_id": prev_action.get("player_id"),
                    "tool": e.get("payload", {}).get("tool"),
                    "error_code": e.get("payload", {}).get("error_code"),
                    "arguments": prev_action.get("payload", {}).get("arguments", {}),
                    "result_summary": e.get("payload", {}).get("result_summary", "")[:200],
                })
                if len(out) >= n:
                    break
    return out


def _extract_obs_categories(events: list[dict]) -> dict[str, int]:
    c: Counter = Counter()
    for e in events:
        if e.get("kind") != "observation":
            continue
        cat = e.get("payload", {}).get("observation_category") or "?"
        c[cat] += 1
    return dict(c)


def _extract_issue621_chain(events: list[dict]) -> dict[str, int]:
    """Issue #621 (down → tend → revive) chain の発火状況。

    trace を文字列レベルで grep して、関連 event/tool の出現数を返す。
    """
    raw = "\n".join(json.dumps(e, ensure_ascii=False) for e in events)
    return {
        "PlayerDownedEvent": raw.count("PlayerDownedEvent"),
        "PlayerRevivedEvent": raw.count("PlayerRevivedEvent"),
        "tend_to_player": raw.count("tend_to_player"),
        "player_revived_post_hoc": raw.count("player_revived_post_hoc"),
        "is_down_true": raw.count('"is_down": true') + raw.count('"is_down":true'),
    }


def _extract_fatigue_trajectory(events: list[dict]) -> dict[str, list[dict]]:
    """疲労値の推移を player_id ごとに 10 tick 毎に取得。

    inner_thought / observation prose から「疲労NN」を正規表現抽出。
    """
    pat = re.compile(r"疲労(\d{1,3})")
    by_pid: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for e in events:
        if e.get("kind") not in ("action", "action_result", "observation"):
            continue
        pid = e.get("player_id")
        if pid is None:
            continue
        blob = json.dumps(e.get("payload", {}), ensure_ascii=False)
        m = pat.search(blob)
        if not m:
            continue
        v = int(m.group(1))
        if 0 <= v <= 100:
            by_pid[pid].append((e.get("tick", 0), v))

    out: dict[str, list[dict]] = {}
    for pid in sorted(by_pid):
        # 10 tick 毎に最新値を保持
        bucket: dict[int, int] = {}
        for t, v in by_pid[pid]:
            bucket[t // 10] = v
        out[f"P{pid}"] = [
            {"tick": b * 10, "fatigue": bucket[b]}
            for b in sorted(bucket)
        ]
    return out


def compute_metrics(run_dir: Path) -> dict[str, Any]:
    events = _load_events(run_dir)
    return {
        "summary": _extract_summary(events),
        "per_player": _extract_per_player(events),
        "per_tool": _extract_per_tool(events),
        "cache_timeseries_20tick": _extract_cache_timeseries(events),
        "per_tick_wall_time_20tick": _bucket_20(_per_tick_wall_times(events)),
        "loop_guard_warnings": _extract_loop_guard(events),
        "fail_examples": _extract_fail_examples(events, n=15),
        "observation_categories": _extract_obs_categories(events),
        "issue621_chain": _extract_issue621_chain(events),
        "fatigue_trajectory_10tick": _extract_fatigue_trajectory(events),
        "total_events": len(events),
    }


def _make_comparison(current: dict, baseline: dict) -> list[dict]:
    """比較表用の単純な行を作る。同名 key を見比べて変化を付ける。"""
    csum = current["summary"]
    bsum = baseline["summary"]
    rows: list[dict] = []
    for label, key, fmt in (
        ("LLM 呼び出し数", "llm_calls", "int"),
        ("p50 latency (s)", "latency_p50_s", "f2"),
        ("prompt tokens", "prompt_tokens_total", "int"),
        ("cached tokens", "cached_tokens_total", "int"),
        ("cache hit 率", "cache_hit_ratio", "pct"),
        ("completion tokens", "completion_tokens_total", "int"),
        ("cost (USD)", "cost_usd_total", "f4"),
        ("action 総数", "action_total", "int"),
        ("失敗率", "action_fail_rate", "pct"),
        ("memo_add", "memo_add", "int"),
        ("memo_done", "memo_done", "int"),
        ("episodic_chunk_written", "episodic_chunk_written", "int"),
        ("short_term_summary", "short_term_summary", "int"),
        ("short_term_long_summary", "short_term_long_summary", "int"),
        ("loop_guard_warning", "loop_guard_warning", "int"),
    ):
        rows.append({
            "label": label,
            "key": key,
            "fmt": fmt,
            "current": csum.get(key),
            "baseline": bsum.get(key),
        })
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_dir", type=Path)
    p.add_argument("baseline_dir", type=Path, nargs="?", default=None)
    p.add_argument("--indent", type=int, default=2)
    args = p.parse_args()

    current = compute_metrics(args.run_dir)
    baseline = compute_metrics(args.baseline_dir) if args.baseline_dir else None

    result = {
        "run_dir": str(args.run_dir),
        "baseline_dir": str(args.baseline_dir) if args.baseline_dir else None,
        "current": current,
        "baseline": baseline,
        "comparison": _make_comparison(current, baseline) if baseline else None,
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=args.indent)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
