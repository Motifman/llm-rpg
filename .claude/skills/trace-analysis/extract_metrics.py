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
import bisect
import itertools
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


# P1 (実験評価の中間指標): survival 系シナリオの進捗を trace から拾う。
# クリア可否 (救助) だけでは「どこまで迫れたか」が見えないため、山頂到達 /
# 狼煙点火 / スポット初訪問の時系列 / 探索の広さ / 注目ランドマークの到達を足す。
_SUMMIT_KEYWORDS = ("山頂", "summit")
# 狼煙点火の検出: signal_fire_lit フラグは trace イベントを持たないため、点火
# interaction の成功メッセージ (survival_island_v2 の狼煙台成功文
# 「…流木に火が回った。狼煙台から白い煙が…」) を目印にする。成功文が変わったら
# ここを直す (analysis 側のヒューリスティックであり、実験挙動には影響しない)。
_SIGNAL_FIRE_KEYWORDS = ("白い煙", "火が回っ")
# 探索の深さを測る名前付きランドマーク (spot_name の部分一致)。spot グラフが
# trace に無く「spawn からのホップ数」は算出できないため、到達 distinct 数と
# これら landmark 到達で深さ/広さを代替する (グラフ距離が要る指標は run_dir だけ
# では出せない — 近似であることを明示)。
_LANDMARK_SPOT_KEYWORDS = ("山頂", "大樫", "見張り台", "廃屋")


def _extract_survival_progress(events: list[dict]) -> dict[str, Any]:
    """survival 系 run の中間到達指標を position_change / action_result から拾う。

    - summit_reached: 山頂スポットに初到達した player とその tick
    - signal_fire_lit_tick: 狼煙点火 (成功メッセージ検出) の最初の tick
    - spot_first_visits: 各スポットへの (誰かの) 初訪問時系列
    - distinct_spots_visited / spots_visited: 探索の広さ
    - landmark_first_visit_tick: 注目ランドマークの初到達 tick (未到達は None)
    """
    scenario = None
    summit_reached: dict[Any, dict[str, Any]] = {}
    signal_fire_tick: int | None = None
    first_visit: dict[str, dict[str, Any]] = {}
    for e in events:
        k = e.get("kind")
        if k == "run_start":
            scenario = e.get("payload", {}).get("scenario")
        elif k == "position_change":
            p = e.get("payload", {})
            spot = p.get("spot_name")
            if not spot:
                continue
            tick = e.get("tick")
            pid = e.get("player_id")
            if spot not in first_visit:
                first_visit[spot] = {"tick": tick, "player_id": pid}
            if any(kw in spot for kw in _SUMMIT_KEYWORDS) and pid not in summit_reached:
                summit_reached[pid] = {"tick": tick, "player_name": p.get("player_name")}
        elif k == "action_result":
            p = e.get("payload", {})
            rs = p.get("result_summary") or ""
            if (
                signal_fire_tick is None
                and p.get("success")
                and any(kw in rs for kw in _SIGNAL_FIRE_KEYWORDS)
            ):
                signal_fire_tick = e.get("tick")

    def _tick_key(t: Any) -> tuple[int, Any]:
        return (1, 0) if t is None else (0, t)

    landmark = {
        kw: next(
            (v["tick"] for s, v in first_visit.items() if kw in s), None
        )
        for kw in _LANDMARK_SPOT_KEYWORDS
    }
    return {
        "scenario": scenario,
        "summit_reached": {
            f"P{pid}": v
            for pid, v in sorted(
                summit_reached.items(), key=lambda kv: _tick_key(kv[0])
            )
        },
        "signal_fire_lit_tick": signal_fire_tick,
        "distinct_spots_visited": len(first_visit),
        "spots_visited": sorted(first_visit.keys()),
        "spot_first_visits": sorted(
            (
                {"tick": v["tick"], "spot_name": s, "player_id": v["player_id"]}
                for s, v in first_visit.items()
            ),
            key=lambda r: _tick_key(r["tick"]),
        ),
        "landmark_first_visit_tick": landmark,
    }


# PR-A (協調シナリオ v3_coop の勝敗判別指標): survival_island_v3_coop で
# 勝ち run (救助成功) と負け run を比べたとき、共在時間や伝聞の流れが人手で毎回
# 計算されていた。勝敗を判別できることが分かった指標を固定して自動集計する。
# 詳細: docs/memory_system (v3_coop 分析ノート) を参照。


def _all_ticks_seen(events: list[dict]) -> list[int]:
    """run 全体で観測された tick の一覧 (昇順・重複なし)。

    ``tick_start`` があれば tick_start を正とする (= 1 tick に 1 件、抜けが
    ない前提)。tick_start が無い trace (合成テスト等) では、他 event が持つ
    tick の最小〜最大の連続範囲で代替する (= 稠密な tick 系列を仮定)。
    """
    starts = {
        e["tick"] for e in events
        if e.get("kind") == "tick_start" and e.get("tick") is not None
    }
    if starts:
        return sorted(starts)
    any_ticks = {e["tick"] for e in events if e.get("tick") is not None}
    if not any_ticks:
        return []
    return list(range(min(any_ticks), max(any_ticks) + 1))


def _reconstruct_player_positions(
    events: list[dict],
) -> dict[int, list[tuple[int, str]]]:
    """``position_change`` から player_id ごとの (tick, to_spot_id) 系列を作る。

    区分一定 (carry-forward) で「その tick に居たスポット」を復元する前提の
    土台。from_spot_id=None の初期配置イベントも to_spot_id は必ず入るため、
    そのまま使える。
    """
    by_pid: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for e in events:
        if e.get("kind") != "position_change":
            continue
        pid = e.get("player_id")
        tick = e.get("tick")
        spot = e.get("payload", {}).get("to_spot_id")
        if pid is None or tick is None or spot is None:
            continue
        by_pid[pid].append((tick, spot))
    for pid in by_pid:
        by_pid[pid].sort(key=lambda x: x[0])
    return by_pid


def _extract_coop_copresence(events: list[dict]) -> dict[str, Any]:
    """ペア別 / 全員同スポットの共在 tick 数を position_change から復元する。

    各 player の位置を carry-forward (直前の to_spot_id を次の position_change
    まで保持) で全 tick に展開し、tick ごとに同一スポットにいる player の組を
    数える。position_change が 1 件も無い player はどの tick でも位置不明とし
    数から除外する (= 過大集計を避ける)。
    """
    by_pid = _reconstruct_player_positions(events)
    if not by_pid:
        return {
            "player_ids": [],
            "player_names": {},
            "tick_count": 0,
            "pair_copresence_ticks": {},
            "all_players_copresence_ticks": 0,
        }

    names: dict[int, str] = {}
    for e in events:
        if e.get("kind") != "position_change":
            continue
        pid = e.get("player_id")
        nm = e.get("payload", {}).get("player_name")
        if pid is not None and nm:
            names[pid] = nm

    pids = sorted(by_pid.keys())
    tick_lists = {pid: [t for t, _ in by_pid[pid]] for pid in pids}
    spot_lists = {pid: [s for _, s in by_pid[pid]] for pid in pids}
    all_ticks = _all_ticks_seen(events)

    pair_counts: dict[str, int] = {
        f"P{a}-P{b}": 0 for a, b in itertools.combinations(pids, 2)
    }
    all_together = 0

    for t in all_ticks:
        positions: dict[int, str] = {}
        for pid in pids:
            idx = bisect.bisect_right(tick_lists[pid], t) - 1
            if idx >= 0:
                positions[pid] = spot_lists[pid][idx]
        for a, b in itertools.combinations(pids, 2):
            sa, sb = positions.get(a), positions.get(b)
            if sa is not None and sb is not None and sa == sb:
                pair_counts[f"P{a}-P{b}"] += 1
        if len(pids) >= 2 and len(positions) == len(pids) and len(set(positions.values())) == 1:
            all_together += 1

    return {
        "player_ids": pids,
        "player_names": {f"P{pid}": names.get(pid) for pid in pids},
        "tick_count": len(all_ticks),
        "pair_copresence_ticks": pair_counts,
        "all_players_copresence_ticks": all_together,
    }


def _extract_hearsay_evidence_by_speaker(events: list[dict]) -> dict[str, Any]:
    """belief_evidence (source_kind=hearsay) を source_speaker 別に集計する。

    伝聞がどの player から流れているかを見る (= 情報伝達の起点の可視化)。
    """
    by_speaker: Counter[str] = Counter()
    for e in events:
        if e.get("kind") != "belief_evidence":
            continue
        p = e.get("payload", {})
        if p.get("source_kind") != "hearsay":
            continue
        speaker = p.get("source_speaker") or "?"
        by_speaker[speaker] += 1
    return {
        "total": sum(by_speaker.values()),
        "by_speaker": dict(by_speaker.most_common()),
    }


def _extract_pending_prediction_verdicts(events: list[dict]) -> dict[str, Any]:
    """約束 (pending_prediction) の kind 別件数と resolved の verdict 内訳。

    ``pending_prediction_*`` kind は将来増える予定 (例: verdict_rejected) の
    ため、既知 kind をハードコードせず prefix match で拾う (= 未知の
    suffix が来ても静かに無視されず件数に乗る)。
    """
    prefix = "pending_prediction_"
    by_kind: Counter[str] = Counter()
    verdicts: Counter[str] = Counter()
    for e in events:
        k = e.get("kind") or ""
        if not k.startswith(prefix):
            continue
        suffix = k[len(prefix):]
        by_kind[suffix] += 1
        if suffix == "resolved":
            v = e.get("payload", {}).get("verdict") or "?"
            verdicts[v] += 1
    return {
        "by_kind": dict(by_kind.most_common()),
        "resolved_verdict_breakdown": dict(verdicts.most_common()),
    }


def _extract_give_item(events: list[dict]) -> dict[str, Any]:
    """give_item (tool=give_item) の action_result を成功/失敗別に数える。"""
    succ = 0
    fail = 0
    for e in events:
        if e.get("kind") != "action_result":
            continue
        p = e.get("payload", {})
        if p.get("tool") != "give_item":
            continue
        if p.get("success", True):
            succ += 1
        else:
            fail += 1
    return {"total": succ + fail, "success": succ, "fail": fail}


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
        "survival_progress": _extract_survival_progress(events),
        "coop_copresence": _extract_coop_copresence(events),
        "coop_hearsay_by_speaker": _extract_hearsay_evidence_by_speaker(events),
        "coop_pending_prediction": _extract_pending_prediction_verdicts(events),
        "coop_give_item": _extract_give_item(events),
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
