"""run と probe を横断して引ける索引を作る。

## なぜ要るか

1 本の run を詳しく見る道具は既にある (``report.md`` / ``trace.html`` /
``analysis.html``)。無いのは **run を横断して引く手段**である。「同じ profile の
run はどれか」「操作名の失敗が多いのはどれか」を知るために、69 個のディレクトリを
開いて数えていた。

## 成果物より長く生きる

``var/`` は gitignore なので、trace は worktree と一緒に消える。索引は commit
するので、成果物が消えた後も「いつ・どの commit で・何を測ったか」が残る。

そのため作り直すとき、**手元に無い run の行を消さない**。別の機材で走らせた run
や、掃除したあとの run の記録が、実行しただけで失われてはいけない。

## 何を入れるか

新しく記録するものは無い。``experiment.config.resolved.json`` と ``trace.jsonl``
に既にあるものを 1 行に畳むだけである。

設定ファイルが無い run も行にする。**黙って落とすと索引が「全部ある」ように
見える。** 条件を復元できない run が在ることまで含めて記録する。

## 使い方

    # 索引を作る / 更新する
    uv run python scripts/build_run_index.py --runs-dir var/runs

    # 引く (当面はこれで足りる)
    jq -r 'select(.profile=="belief_goal_full") | .id' docs/experiments/run_index.jsonl
    jq -r '.metrics.failures_by_code.INTERACTION_ACTION_NOT_FOUND // 0' \\
        docs/experiments/run_index.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: 索引の既定の置き場。**commit する。**
#:
#: ``var/`` に置くと gitignore されて、索引そのものが成果物と一緒に消える。
#: それでは「成果物より長く生きる」という目的を果たせない。
DEFAULT_INDEX = Path("docs/experiments/run_index.jsonl")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _summarize_trace(path: Path) -> dict[str, Any]:
    """trace を 1 回舐めて、横断で引きたい数だけを数える。

    壊れた行は数えて飛ばす。途中で例外にすると、1 行の破損で索引全体が
    作れなくなる。
    """
    kinds: Counter = Counter()
    failures: Counter = Counter()
    action_results = 0
    unreadable = 0
    ticks: list[int] = []
    try:
        handle = path.open(errors="replace")
    except OSError:
        return {"unreadable_lines": 0, "kinds": {}}
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                unreadable += 1
                continue
            if not isinstance(event, dict):
                unreadable += 1
                continue
            kinds[event.get("kind")] += 1
            tick = event.get("tick")
            if isinstance(tick, int):
                ticks.append(tick)
            payload = event.get("payload") or {}
            if event.get("kind") != "action_result":
                continue
            action_results += 1
            if payload.get("success") is False:
                failures[str(payload.get("error_code") or "UNKNOWN")] += 1
    return {
        "action_results": action_results,
        "action_failures": sum(failures.values()),
        "failures_by_code": dict(failures.most_common()),
        "llm_calls": kinds.get("llm_call", 0) or kinds.get("action", 0),
        "events_total": sum(kinds.values()),
        "last_tick": max(ticks) if ticks else None,
        "unreadable_lines": unreadable,
    }


def build_index(runs_dir: Path) -> list[dict[str, Any]]:
    """``runs_dir`` 配下の run を 1 行ずつに畳む。"""
    rows: list[dict[str, Any]] = []
    for trace in sorted(Path(runs_dir).glob("*/trace.jsonl")):
        run_dir = trace.parent
        config = _read_json(run_dir / "experiment.config.resolved.json")
        git = (config or {}).get("git") or {}
        runtime_config = (config or {}).get("runtime_config") or {}
        scenario_path = str((config or {}).get("scenario_path") or "")
        rows.append(
            {
                "kind": "run",
                "id": run_dir.name,
                "measured_at": datetime.fromtimestamp(os.path.getmtime(trace), tz=timezone.utc).isoformat(
                    timespec="seconds"
                ),
                # 設定ファイルが無い run は条件を復元できない。**後から埋め
                # られないので、埋まらないことを記録する。**
                "conditions_recoverable": config is not None,
                "git_commit": git.get("commit"),
                "git_dirty": git.get("dirty"),
                "profile": (config or {}).get("profile"),
                "scenario": os.path.basename(scenario_path) or None,
                "scenario_sha256": (config or {}).get("scenario_sha256"),
                "max_world_ticks": (config or {}).get("max_world_ticks"),
                "model": runtime_config.get("llm_model"),
                "typed_judgment_provider": runtime_config.get("typed_judgment_provider"),
                "metrics": _summarize_trace(trace),
                "artifacts": str(run_dir),
            }
        )
    return rows


def read_index(path: Path) -> list[dict[str, Any]]:
    """索引を読む。無ければ空。"""
    if not Path(path).exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def write_index(path: Path, rows: Sequence[dict[str, Any]], *, merge: bool = False) -> list[dict[str, Any]]:
    """索引を書く。``merge`` なら既存の行を残したまま差し替える。

    **手元に無い run の行を消さない。** 索引は成果物より長く生きるためのもの
    なので、作り直しただけで過去の記録が失われては意味がない。

    Returns:
        書き込んだ全行 (id 順)。
    """
    for row in rows:
        if not row.get("id"):
            raise ValueError("index row must have an id")
    merged: dict[str, dict[str, Any]] = {}
    if merge:
        for row in read_index(path):
            if row.get("id"):
                merged[str(row["id"])] = row
    for row in rows:
        merged[str(row["id"])] = dict(row)
    # 並びを id で固定する。作り直すたびに差分が出ると、commit の diff が
    # 読めなくなる。
    ordered = [merged[key] for key in sorted(merged)]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in ordered))
    return ordered


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", default="var/runs")
    parser.add_argument("--index", default=str(DEFAULT_INDEX))
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="既存の行を残さず入れ替える (通常は使わない)",
    )
    args = parser.parse_args(argv)

    rows = build_index(Path(args.runs_dir))
    written = write_index(Path(args.index), rows, merge=not args.no_merge)
    recoverable = sum(1 for r in written if r.get("conditions_recoverable"))
    print(f"走査した run: {len(rows)} 件")
    print(f"索引の行数: {len(written)} 件 (条件を復元できる: {recoverable} 件)")
    print(f"-> {args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
