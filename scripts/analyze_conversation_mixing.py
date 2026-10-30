#!/usr/bin/env python3
"""trace.jsonl の speech イベントから「会話の混線」シグナルを集計する。

実験 #25 (#356) で観測された問題: 同 spot に複数 LLM agent がいると、
発言 (speech_speak action) と他者がそれを聞く observation の間に
複数 tick の lag が入り、「2 ターン前の話題に唐突に返事する」「並列の
別会話に割り込む」といった現実離れした会話が混ざる。

このスクリプトは以下を JSONL から集計し、markdown レポートに書き出す:

- **発言件数** (player 別 / spot 別)
- **連続発言**: 同 player が直近 N tick 連続で speech_speak している
  (相手の応答を待たずに話し続ける lag)
- **反応 lag 分布**: speech observation の到来 tick と、その recipient の
  次の speech_speak action までの delta tick (p50 / p95 / p99 / max)
- **クロストーク**: 同一 spot で 1 tick 内に複数 player が同時発言した件数

trace から会議の混線を数えるスクリプト。
trace に kind=action / observation が出ている前提で動く。

使い方::

    python scripts/analyze_conversation_mixing.py var/runs/exp25/trace.jsonl

    # markdown report も書く:
    python scripts/analyze_conversation_mixing.py trace.jsonl --markdown report.md

    # 複数 run を比較:
    python scripts/analyze_conversation_mixing.py run1/trace.jsonl run2/trace.jsonl
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, TextIO

SPEECH_TOOL_PREFIX = "speech_"
SPEECH_OBSERVATION_CATEGORY = "speech"


def iter_trace_events(paths: Sequence[Path]) -> Iterable[dict[str, Any]]:
    """JSONL 群を 1 件ずつ dict として yield。壊れた行は skip。"""
    for p in paths:
        with p.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # 壊れた 1 行で集計を止めない方を優先
                    continue


def extract_speech_actions(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """kind=action かつ tool が speech_ で始まる event を取り出す。"""
    out: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("kind") != "action":
            continue
        payload = ev.get("payload") or {}
        tool = str(payload.get("tool") or "")
        if not tool.startswith(SPEECH_TOOL_PREFIX):
            continue
        out.append(ev)
    return out


def extract_speech_observations(
    events: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """kind=observation かつ category=speech の event を取り出す。"""
    out: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("kind") != "observation":
            continue
        payload = ev.get("payload") or {}
        if payload.get("observation_category") != SPEECH_OBSERVATION_CATEGORY:
            continue
        out.append(ev)
    return out


def count_by_player(events: list[dict[str, Any]]) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for ev in events:
        pid = ev.get("player_id")
        if pid is None:
            continue
        counts[int(pid)] += 1
    return dict(counts)


def consecutive_runs(
    actions: list[dict[str, Any]],
) -> dict[int, list[int]]:
    """player 別の「連続発言 tick 数」のリストを返す。

    同じ player が tick T, T+1, T+2 と続けて speech_ すると、長さ 3 の
    run として記録する。
    """
    # player_id → sorted list of unique ticks where they spoke
    by_player_ticks: dict[int, list[int]] = defaultdict(list)
    for ev in actions:
        pid = ev.get("player_id")
        tick = ev.get("tick")
        if pid is None or tick is None:
            continue
        by_player_ticks[int(pid)].append(int(tick))

    out: dict[int, list[int]] = {}
    for pid, ticks in by_player_ticks.items():
        ticks = sorted(set(ticks))
        runs: list[int] = []
        if not ticks:
            out[pid] = runs
            continue
        run = 1
        for prev, cur in itertools.pairwise(ticks):
            if cur == prev + 1:
                run += 1
            else:
                if run > 1:
                    runs.append(run)
                run = 1
        if run > 1:
            runs.append(run)
        out[pid] = runs
    return out


def reply_lags(
    observations: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> list[int]:
    """speech observation 到来 tick → その recipient の次 speech_speak action までの delta。

    recipient = observation の player_id。LLM の prompt はその tick に組み立てられ
    るので、observation を見てから返事するまで何 tick 待つかが reply lag に近い。
    """
    # player_id → sorted list of action ticks
    actions_by_player: dict[int, list[int]] = defaultdict(list)
    for ev in actions:
        pid = ev.get("player_id")
        tick = ev.get("tick")
        if pid is None or tick is None:
            continue
        actions_by_player[int(pid)].append(int(tick))
    for pid in actions_by_player:
        actions_by_player[pid].sort()

    lags: list[int] = []
    for ob in observations:
        pid = ob.get("player_id")
        tick = ob.get("tick")
        if pid is None or tick is None:
            continue
        speaker_ticks = actions_by_player.get(int(pid), [])
        # 二分探索で「tick 以上の最初の action tick」を取る
        lo, hi = 0, len(speaker_ticks)
        while lo < hi:
            mid = (lo + hi) // 2
            if speaker_ticks[mid] < int(tick):
                lo = mid + 1
            else:
                hi = mid
        if lo < len(speaker_ticks):
            lag = speaker_ticks[lo] - int(tick)
            lags.append(lag)
    return lags


def crosstalk_count(actions: list[dict[str, Any]]) -> dict[int, int]:
    """tick → その tick に発言した player の数 (>=2 のものだけ返す)。

    同 spot 判定までは厳密にやらず、tick-only でカウント (cross-spot で
    たまたま同 tick に発言した分も込みのラフ推定)。実験 #25 では 4 人で
    spot が同じことが多いので、十分シグナルになる。
    """
    by_tick_players: dict[int, set] = defaultdict(set)
    for ev in actions:
        tick = ev.get("tick")
        pid = ev.get("player_id")
        if tick is None or pid is None:
            continue
        by_tick_players[int(tick)].add(int(pid))
    return {t: len(p) for t, p in by_tick_players.items() if len(p) >= 2}


def percentiles(values: list[int], pcts: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {f"p{int(p)}": None for p in pcts}
    sorted_v = sorted(values)
    n = len(sorted_v)
    out: dict[str, float | None] = {}
    for p in pcts:
        idx = max(0, min(n - 1, round((p / 100.0) * (n - 1))))
        out[f"p{int(p)}"] = float(sorted_v[idx])
    return out


def summarize(paths: Sequence[Path]) -> dict[str, Any]:
    events = list(iter_trace_events(paths))
    actions = extract_speech_actions(events)
    observations = extract_speech_observations(events)
    runs = consecutive_runs(actions)
    lags = reply_lags(observations, actions)
    crosstalk = crosstalk_count(actions)

    summary: dict[str, Any] = {
        "trace_files": [str(p) for p in paths],
        "total_speech_actions": len(actions),
        "total_speech_observations": len(observations),
        "speech_actions_by_player": count_by_player(actions),
        "speech_observations_by_player": count_by_player(observations),
        "consecutive_runs_by_player": {
            pid: {
                "run_count": len(rs),
                "max_run": (max(rs) if rs else 0),
                "mean_run": (statistics.mean(rs) if rs else 0.0),
            }
            for pid, rs in runs.items()
        },
        "reply_lag_ticks": {
            "count": len(lags),
            "mean": (statistics.mean(lags) if lags else None),
            "max": (max(lags) if lags else None),
            **percentiles(lags, [50, 95, 99]),
        },
        "crosstalk_ticks": {
            "tick_count_with_2plus_speakers": len(crosstalk),
            "max_speakers_in_one_tick": (max(crosstalk.values()) if crosstalk else 0),
        },
    }
    return summary


def write_markdown(summary: dict[str, Any], out: TextIO) -> None:
    out.write("# 会話混線分析レポート\n\n")
    out.write(f"対象 trace: {summary['trace_files']}\n\n")
    out.write("## 全体\n\n")
    out.write(f"- speech_speak action: **{summary['total_speech_actions']}** 件\n")
    out.write(f"- speech observation: **{summary['total_speech_observations']}** 件\n\n")

    out.write("## player 別 発言/被発言\n\n")
    out.write("| player_id | speak | observe |\n|---|---|---|\n")
    pids = sorted(set(summary["speech_actions_by_player"]) | set(summary["speech_observations_by_player"]))
    for pid in pids:
        s = summary["speech_actions_by_player"].get(pid, 0)
        o = summary["speech_observations_by_player"].get(pid, 0)
        out.write(f"| {pid} | {s} | {o} |\n")
    out.write("\n")

    out.write("## 連続発言 run (相手の返事を待たず話し続ける)\n\n")
    out.write("| player_id | run_count | max_run | mean_run |\n|---|---|---|---|\n")
    for pid, info in summary["consecutive_runs_by_player"].items():
        out.write(f"| {pid} | {info['run_count']} | {info['max_run']} | {info['mean_run']:.2f} |\n")
    out.write("\n")

    rl = summary["reply_lag_ticks"]
    out.write("## 反応 lag (speech observation → 同 player 次 speech_speak まで)\n\n")

    # count=0 (= 該当 observation 無し / 該当 recipient の action 無し) では
    # mean / p50 / p95 / p99 / max が全部 None になる。markdown 上は "—" で
    # 表現し「データなし」を明示する (code-review MEDIUM 対応)。
    def _fmt(v: Any) -> str:
        return "—" if v is None else str(v)

    out.write(f"- 観測数: {rl['count']}\n")
    out.write(f"- mean: {_fmt(rl['mean'])}\n")
    out.write(
        f"- p50 / p95 / p99 / max: "
        f"{_fmt(rl.get('p50'))} / {_fmt(rl.get('p95'))} / "
        f"{_fmt(rl.get('p99'))} / {_fmt(rl['max'])}\n\n"
    )

    ct = summary["crosstalk_ticks"]
    out.write("## クロストーク (同 tick に 2 人以上が発言)\n\n")
    out.write(f"- 2 人以上同 tick 発言の tick 数: **{ct['tick_count_with_2plus_speakers']}**\n")
    out.write(f"- 1 tick あたり最大 speaker 数: **{ct['max_speakers_in_one_tick']}**\n")


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace_files", nargs="+", type=Path, help="trace.jsonl path(s)")
    p.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="markdown report の出力先 (省略時は stdout に JSON で出す)",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    for p in args.trace_files:
        if not p.exists():
            print(f"trace file が存在しない: {p}", file=sys.stderr)
            return 2
    summary = summarize(args.trace_files)
    if args.markdown is not None:
        with args.markdown.open("w", encoding="utf-8") as f:
            write_markdown(summary, f)
        print(f"markdown report を書き出した: {args.markdown}", file=sys.stderr)
    else:
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
