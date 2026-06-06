#!/usr/bin/env python3
"""trace.jsonl の LLM_CALL event から LLM 性能指標を集計する (PR #358 後続)。

実験 #25 (#356) 等で τ_sim 設定根拠 / モデル比較 / scenario cost を分析するための
post-hoc 集計ツール。

使い方::

    python scripts/analyze_llm_latency.py var/runs/issue356_experiment25_off_r1/trace.jsonl

    # markdown report も書き出す:
    python scripts/analyze_llm_latency.py trace.jsonl --markdown report.md

    # 複数 run をまとめて比較:
    python scripts/analyze_llm_latency.py run1/trace.jsonl run2/trace.jsonl

集計指標:
    - **全体**: 呼び出し総数、成功率
    - **wall_latency_ms**: 壁時計レイテンシ (p50 / p95 / p99 / max / mean)
    - **TPS**: 出力トークン速度
    - **tokens**: 入力 / 出力トークン数の分布
    - **breakdown**: player_id / model / error_code 別の小計

τ_sim 設計の参考になる値:
    - wall_latency p95 → これ以下に τ_sim を設定すると LOST_RACE 多発
    - wall_latency p99 → これ以上にすると idle 時間が長すぎる
    - 推奨は p95 と p99 の中間
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, TextIO


# LLM_CALL event を絞り込む kind 値。
# trace events.py の TraceEventKind.LLM_CALL と同値。
LLM_CALL_KIND = "llm_call"


def iter_llm_call_events(trace_paths: Sequence[Path]) -> Iterable[Dict[str, Any]]:
    """1 件以上の trace.jsonl から LLM_CALL event だけを順に返す。

    壊れた行 / 別 kind / payload 欠落は黙って skip する (集計が止まらない方を優先)。
    """
    for path in trace_paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("kind") != LLM_CALL_KIND:
                        continue
                    yield event
        except OSError:
            print(f"warning: {path} を開けませんでした", file=sys.stderr)
            continue


def _percentile(values: Sequence[float], p: float) -> Optional[float]:
    """0..100 のパーセンタイル。values 空なら None。

    statistics.quantiles は n=100 で 99 値を返すので、p=95 なら values[94] を取る。
    n が極端に小さい (< 100) でも線形補完で出る。
    """
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    # 線形補完: p=50 → 中央。p=99 → 上位 1%。
    k = (len(sorted_values) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = k - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def _summarize(values: Sequence[float]) -> Dict[str, Optional[float]]:
    """値リストから p50 / p95 / p99 / max / mean を辞書で返す。"""
    if not values:
        return {
            "count": 0,
            "p50": None,
            "p95": None,
            "p99": None,
            "max": None,
            "mean": None,
        }
    return {
        "count": len(values),
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
        "p99": _percentile(values, 99),
        "max": max(values),
        "mean": statistics.mean(values),
    }


def _fmt_ms(x: Optional[float]) -> str:
    if x is None:
        return "-"
    return f"{x:.0f}ms"


def _fmt_float(x: Optional[float], digits: int = 2) -> str:
    if x is None:
        return "-"
    return f"{x:.{digits}f}"


def _fmt_int(x: Optional[float]) -> str:
    if x is None:
        return "-"
    return f"{int(x)}"


def analyze(trace_paths: Sequence[Path]) -> Dict[str, Any]:
    """全 LLM_CALL event を集計して dict を返す。

    返り値の構造:
        {
            "total_calls": int,
            "success_count": int,
            "failure_count": int,
            "overall": {wall_latency_ms / tps / prompt_tokens / completion_tokens の summary},
            "by_model": {model: summary},
            "by_player": {player_id: summary},
            "by_error_code": {error_code: count},
        }
    """
    wall_latencies: List[float] = []
    tps_values: List[float] = []
    prompt_tokens: List[float] = []
    completion_tokens: List[float] = []

    by_model_wall: Dict[str, List[float]] = defaultdict(list)
    by_player_wall: Dict[int, List[float]] = defaultdict(list)
    by_error_code: Dict[str, int] = defaultdict(int)

    success_count = 0
    failure_count = 0

    for event in iter_llm_call_events(trace_paths):
        payload = event.get("payload") or {}
        # payload 内 / event トップレベル両対応 (record() は **kwargs を payload に詰める)
        def _get(key: str) -> Any:
            return payload.get(key, event.get(key))

        wall = _get("wall_latency_ms")
        tps = _get("tps")
        prompt = _get("prompt_tokens")
        completion = _get("completion_tokens")
        model = _get("model") or "unknown"
        player_id = event.get("player_id")
        success = _get("success")
        error_code = _get("error_code")

        if success:
            success_count += 1
        else:
            failure_count += 1
            if error_code:
                by_error_code[str(error_code)] += 1

        if isinstance(wall, (int, float)) and wall >= 0:
            wall_latencies.append(float(wall))
            by_model_wall[str(model)].append(float(wall))
            if isinstance(player_id, int):
                by_player_wall[player_id].append(float(wall))
        if isinstance(tps, (int, float)) and tps > 0:
            tps_values.append(float(tps))
        if isinstance(prompt, (int, float)) and prompt >= 0:
            prompt_tokens.append(float(prompt))
        if isinstance(completion, (int, float)) and completion >= 0:
            completion_tokens.append(float(completion))

    return {
        "total_calls": success_count + failure_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "overall": {
            "wall_latency_ms": _summarize(wall_latencies),
            "tps": _summarize(tps_values),
            "prompt_tokens": _summarize(prompt_tokens),
            "completion_tokens": _summarize(completion_tokens),
        },
        "by_model": {m: _summarize(v) for m, v in by_model_wall.items()},
        "by_player": {pid: _summarize(v) for pid, v in by_player_wall.items()},
        "by_error_code": dict(by_error_code),
    }


def render_report(stats: Dict[str, Any]) -> str:
    """analyze 結果を markdown report 文字列にする。"""
    lines: List[str] = []
    total = stats["total_calls"]
    success = stats["success_count"]
    failure = stats["failure_count"]
    success_rate = (success / total * 100.0) if total > 0 else 0.0

    lines.append("# LLM Call Latency Analysis")
    lines.append("")
    lines.append(f"- **総呼び出し**: {total}")
    lines.append(f"- **成功**: {success} ({success_rate:.1f}%)")
    lines.append(f"- **失敗**: {failure}")
    lines.append("")

    overall = stats["overall"]
    wall = overall["wall_latency_ms"]
    tps = overall["tps"]
    prompt = overall["prompt_tokens"]
    completion = overall["completion_tokens"]

    lines.append("## 全体サマリ")
    lines.append("")
    lines.append("| 指標 | count | p50 | p95 | p99 | max | mean |")
    lines.append("|---|---|---|---|---|---|---|")
    lines.append(
        f"| wall_latency_ms | {_fmt_int(wall['count'])} | "
        f"{_fmt_ms(wall['p50'])} | {_fmt_ms(wall['p95'])} | "
        f"{_fmt_ms(wall['p99'])} | {_fmt_ms(wall['max'])} | {_fmt_ms(wall['mean'])} |"
    )
    lines.append(
        f"| TPS | {_fmt_int(tps['count'])} | "
        f"{_fmt_float(tps['p50'])} | {_fmt_float(tps['p95'])} | "
        f"{_fmt_float(tps['p99'])} | {_fmt_float(tps['max'])} | {_fmt_float(tps['mean'])} |"
    )
    lines.append(
        f"| prompt_tokens | {_fmt_int(prompt['count'])} | "
        f"{_fmt_int(prompt['p50'])} | {_fmt_int(prompt['p95'])} | "
        f"{_fmt_int(prompt['p99'])} | {_fmt_int(prompt['max'])} | {_fmt_float(prompt['mean'], 1)} |"
    )
    lines.append(
        f"| completion_tokens | {_fmt_int(completion['count'])} | "
        f"{_fmt_int(completion['p50'])} | {_fmt_int(completion['p95'])} | "
        f"{_fmt_int(completion['p99'])} | {_fmt_int(completion['max'])} | {_fmt_float(completion['mean'], 1)} |"
    )
    lines.append("")

    by_model = stats["by_model"]
    if by_model:
        lines.append("## Model 別 wall_latency_ms")
        lines.append("")
        lines.append("| model | count | p50 | p95 | p99 | mean |")
        lines.append("|---|---|---|---|---|---|")
        for model, summary in sorted(by_model.items()):
            lines.append(
                f"| `{model}` | {_fmt_int(summary['count'])} | "
                f"{_fmt_ms(summary['p50'])} | {_fmt_ms(summary['p95'])} | "
                f"{_fmt_ms(summary['p99'])} | {_fmt_ms(summary['mean'])} |"
            )
        lines.append("")

    by_player = stats["by_player"]
    if by_player:
        lines.append("## Player 別 wall_latency_ms")
        lines.append("")
        lines.append("| player_id | count | p50 | p95 | p99 | mean |")
        lines.append("|---|---|---|---|---|---|")
        for pid, summary in sorted(by_player.items()):
            lines.append(
                f"| {pid} | {_fmt_int(summary['count'])} | "
                f"{_fmt_ms(summary['p50'])} | {_fmt_ms(summary['p95'])} | "
                f"{_fmt_ms(summary['p99'])} | {_fmt_ms(summary['mean'])} |"
            )
        lines.append("")

    by_error = stats["by_error_code"]
    if by_error:
        lines.append("## 失敗内訳")
        lines.append("")
        lines.append("| error_code | count |")
        lines.append("|---|---|")
        for code, count in sorted(by_error.items(), key=lambda kv: -kv[1]):
            lines.append(f"| `{code}` | {count} |")
        lines.append("")

    # τ_sim 設計の手がかり (overall wall_latency が出ているときだけ)
    if wall["p95"] is not None and wall["p99"] is not None:
        recommended = (wall["p95"] + wall["p99"]) / 2.0 / 1000.0
        lines.append("## τ_sim 設計の手がかり")
        lines.append("")
        lines.append(
            f"- p95 = {_fmt_ms(wall['p95'])}、p99 = {_fmt_ms(wall['p99'])}"
        )
        lines.append(
            f"- **推奨 τ_sim ≈ {recommended:.1f}s** (= (p95+p99)/2)"
        )
        lines.append(
            "- τ_sim ≤ p95 は LOST_RACE / STALE 多発、τ_sim ≥ p99 は idle 時間が支配的"
        )
        lines.append("")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="trace.jsonl の LLM_CALL event を集計して latency / TPS / token 分布を出す",
    )
    parser.add_argument(
        "trace_paths",
        type=Path,
        nargs="+",
        help="trace.jsonl のパス (複数指定で結合集計)",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Markdown report を書き出すパス (指定しない場合は stdout)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="生 stats を JSON で書き出すパス (集計結果を pandas/外部ツールに渡す用)",
    )
    args = parser.parse_args(argv)

    # path validation
    missing = [p for p in args.trace_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"error: trace 不在: {p}", file=sys.stderr)
        return 2

    stats = analyze(args.trace_paths)
    report = render_report(stats)

    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(report, encoding="utf-8")
        print(f"[markdown] {args.markdown}", file=sys.stderr)
    else:
        # stdout
        print(report)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[json] {args.json}", file=sys.stderr)

    if stats["total_calls"] == 0:
        print(
            "warning: LLM_CALL event が見つかりません (trace が古い / 並列化なしの run の可能性)",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
