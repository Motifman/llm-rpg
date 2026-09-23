"""過去 run の「存在しない tool 名」の失敗を組み直し、Jev がどの tool を提案するかを記録する (#1413)。

## 何を組み直すか

``error_code=UNSUPPORTED_TOOL`` の ``action_result`` ごとに、同じ player の直前の
``action`` から引数を、直前の ``llm_call`` から送った tool 名 (``tool_names``) を取る。

送った tool の説明文は trace に残っていない。run が使ったシナリオで今の runtime を
組み、会議中と会議外の tool 定義から引く。組めない古いシナリオは、今の
``data/scenarios`` の定義の和集合で埋める。**当時の説明と一致する保証はない。**
今の定義に無い名前は説明なしのまま選択肢に入れる。

判断は本番と同じ ``ToolNameRescue`` を通す。

## 使い方

    # 1. 事例を切り出す (API を呼ばない)
    uv run python scripts/jev_tool_name_rescue_demo.py extract \\
        --runs-dir ../../var/runs --out var/jev_tool_name_demo/cases.json

    # 2. 実際に Jev へ問う (課金あり)
    uv run python scripts/jev_tool_name_rescue_demo.py run \\
        --cases var/jev_tool_name_demo/cases.json --out var/jev_tool_name_demo/results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))


@dataclass
class Case:
    run: str
    tick: int | None
    player_id: int | None
    requested: str
    arguments: dict[str, Any]
    offered: dict[str, str | None]
    offered_source: str
    scenario_path: str = ""
    missing_descriptions: list[str] = field(default_factory=list)


def _load_events(path: Path) -> list[dict]:
    out = []
    for line in path.open():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _preceding(events: Sequence[dict], index: int, kind: str) -> dict:
    player = events[index].get("player_id")
    for j in range(index - 1, -1, -1):
        c = events[j]
        if c.get("kind") == kind and c.get("player_id") == player:
            return c.get("payload") or {}
    return {}


def _scenario_path(run_dir: Path) -> Path | None:
    config = run_dir / "experiment.config.resolved.json"
    if config.exists():
        try:
            raw = json.loads(config.read_text()).get("scenario_path")
        except (json.JSONDecodeError, OSError):
            raw = None
        if raw:
            for base in (_REPO_ROOT, _REPO_ROOT.parent.parent.parent):
                if (base / raw).exists():
                    return base / raw
    copied = run_dir / "scenario.json"
    return copied if copied.exists() else None


_DESCRIPTION_CACHE: dict[str, dict[str, str | None]] = {}


def _descriptions(scenario: Path | None) -> dict[str, str | None]:
    """シナリオで組んだ今の runtime の、会議中と会議外の tool 名 → 説明の 1 行目。"""
    if scenario is None:
        return {}
    key = str(scenario)
    if key in _DESCRIPTION_CACHE:
        return _DESCRIPTION_CACHE[key]
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    out: dict[str, str | None] = {}
    try:
        runtime = create_world_runtime(scenario)
        for as_meeting in (False, True):
            for d in runtime.get_tool_definitions(
                as_meeting_phase=as_meeting, for_every_player=True
            ):
                lines = d.description.strip().splitlines()
                out.setdefault(d.name, lines[0].strip() if lines else None)
    except Exception as exc:  # 古いシナリオが今の engine で組めないことがある
        print(f"warning: {scenario}: {exc}", file=sys.stderr)
    _DESCRIPTION_CACHE[key] = out
    return out


def _catalog() -> dict[str, str | None]:
    """今の ``data/scenarios`` で組める runtime の tool 説明の和集合。

    古い run のシナリオは今の engine で組めないことがあるので、その縮退先に使う。
    """
    out: dict[str, str | None] = {}
    for scenario in sorted((_REPO_ROOT / "data" / "scenarios").glob("*.json")):
        for name, description in _descriptions(scenario).items():
            if description:
                out.setdefault(name, description)
    return out


def _listed_in_message(message: str) -> list[str]:
    marker = "現在使える tool: ["
    if marker not in message:
        return []
    inner = message.split(marker, 1)[1].rsplit("]", 1)[0]
    return [n.strip() for n in inner.split(",") if n.strip()]


def extract_cases(runs_dir: Path) -> list[Case]:
    cases: list[Case] = []
    for trace in sorted(runs_dir.glob("*/trace.jsonl")):
        events = _load_events(trace)
        scenario = _scenario_path(trace.parent)
        for i, e in enumerate(events):
            p = e.get("payload") or {}
            if e.get("kind") != "action_result" or p.get("error_code") != "UNSUPPORTED_TOOL":
                continue
            names = list(_preceding(events, i, "llm_call").get("tool_names") or [])
            source = "llm_call.tool_names"
            if not names:
                # 送った一覧が残っていない run は、失敗文の一覧 (handler 表由来で
                # 送った一覧より広い) で代用する。
                names = _listed_in_message(p.get("result_summary") or "")
                source = "result_summary"
            descriptions = {**_catalog(), **{k: v for k, v in _descriptions(scenario).items() if v}}
            offered = {n: descriptions.get(n) for n in names}
            cases.append(Case(
                run=trace.parent.name,
                tick=e.get("tick"),
                player_id=e.get("player_id"),
                requested=str(p.get("tool") or ""),
                arguments=dict(_preceding(events, i, "action").get("arguments") or {}),
                offered=offered,
                offered_source=source,
                scenario_path=str(scenario or ""),
                missing_descriptions=[n for n, d in offered.items() if not d],
            ))
    return cases


def cmd_extract(args: argparse.Namespace) -> int:
    cases = extract_cases(Path(args.runs_dir))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([asdict(c) for c in cases], ensure_ascii=False, indent=1))
    print(f"cases: {len(cases)} → {out}")
    for c in cases:
        print(f"  {c.run} t={c.tick} {c.requested} ({c.offered_source}, 送った {len(c.offered)} 件, 説明なし {len(c.missing_descriptions)})")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    load_dotenv(_REPO_ROOT.parent.parent.parent / ".env")
    from ai_rpg_world.application.llm.services.world_llm_turn.tool_name_rescue import (
        ToolNameRescue,
        suggest_closest_tool_name,
    )
    from ai_rpg_world.application.llm.wiring._typed_judgment_factory import (
        create_typed_judgment_port_from_config,
    )
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
        ResolvedLlmRuntimeConfig,
    )

    port = create_typed_judgment_port_from_config(
        ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="jev")
    )
    rescue = ToolNameRescue(port=port, min_confidence=args.min_confidence)
    cases = [Case(**c) for c in json.loads(Path(args.cases).read_text())]
    results = []
    for c in cases:
        suggestion = rescue.suggest(c.requested, offered=c.offered, arguments=c.arguments)
        results.append({
            "case": asdict(c),
            "similarity": suggest_closest_tool_name(c.requested, c.offered),
            "judgment": suggestion.trace_payload(),
        })
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"min_confidence": args.min_confidence, "results": results},
        ensure_ascii=False, indent=1,
    ))
    print(f"事例 {len(results)} 件 (閾値 {args.min_confidence}) → {out}")
    for r in results:
        c, j = r["case"], r["judgment"] or {}
        prob = (j.get("probabilities") or {}).get(str(j.get("chosen")))
        print(
            f"{c['requested']:<24} → 判断 {j.get('chosen')!s:<12} "
            f"(確率 {prob} / 確信 {j.get('confidence')}) "
            f"提案 {j.get('suggested')!s:<12} [{j.get('suggestion_source')}] "
            f"縮退 {j.get('fallback_reason')} {j.get('unavailable_reason') or ''} | 類似度 {r['similarity']}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pe = sub.add_parser("extract")
    pe.add_argument("--runs-dir", required=True)
    pe.add_argument("--out", default="var/jev_tool_name_demo/cases.json")
    pe.set_defaults(func=cmd_extract)
    pr = sub.add_parser("run")
    pr.add_argument("--cases", default="var/jev_tool_name_demo/cases.json")
    pr.add_argument("--out", default="var/jev_tool_name_demo/results.json")
    pr.add_argument("--min-confidence", type=float, default=0.7)
    pr.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
