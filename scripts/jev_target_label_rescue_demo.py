"""過去 run の「対象の名前が解決できなかった」失敗を、Jev が救えるかを実データで測る。

行動名の救済 (scripts/jev_action_name_rescue_demo.py、#1331) と同じ問いを、
`target_label` / `item_label` (対象物・手持ちの品・足元の品) に向ける。

- 事例: `INVALID_TARGET_LABEL` で失敗し、失敗文に候補一覧が載っているもの。
  暗くて見えない失敗と、候補が空の失敗は救済の対象外なので落とす
- 候補の説明: その run のシナリオ JSON から、対象物と品目の description を引く
- 対照: 書かれた名前を、無関係な事例の候補一覧と組み合わせる。正解を持たない
  組で何かを選ぶ割合が誤救済率の上限

使い方:
    uv run python scripts/jev_target_label_rescue_demo.py extract --runs-dir ../../../var/runs --out var/jev_label_demo/cases.json
    uv run python scripts/jev_target_label_rescue_demo.py run --cases var/jev_label_demo/cases.json --out var/jev_label_demo/results.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

_NO_MATCH = "__no_match__"
_TOOLS = ("interact", "use_item", "give_item", "pickup_item", "drop_item")

# 失敗文の形式。engine の世代で 4 つある。
_PATTERNS = (
    re.compile(r"(?:対象の名前|オブジェクト名|オブジェクトラベル)が見つかりません: (?P<written>.*?)。有効な (?:target_label|object_label): (?P<cands>.+)$", re.S),
    re.compile(r"指定された(?P<kind>[^は]+?)は現在の候補にありません: (?P<written>.*?) → 有効な[^:]+: (?P<cands>.+)$", re.S),
)


@dataclass
class Case:
    run: str
    tick: int | None
    player_id: int | None
    tool: str
    written: str
    inner_thought: str
    candidates: dict[str, str]  # 名前 → 説明 (無ければ "")
    scenario_path: str = ""
    is_control: bool = False
    borrowed_from: str | None = None


@dataclass
class Outcome:
    method: str
    chosen: str | None
    raw_choice: str | None = None
    score: float | None = None
    confidence: float | None = None
    latency_ms: float | None = None
    error: str | None = None


def _load_events(path: Path) -> list[dict]:
    out = []
    for line in path.open():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _preceding_action(events: Sequence[dict], index: int) -> dict:
    failure = events[index]
    for j in range(index - 1, max(-1, index - 8), -1):
        c = events[j]
        if c.get("kind") == "action" and c.get("player_id") == failure.get("player_id"):
            return c.get("payload") or {}
    return {}


def _run_scenario(run_dir: Path) -> str:
    config = run_dir / "experiment.config.resolved.json"
    if not config.exists():
        return ""
    try:
        return str(json.loads(config.read_text()).get("scenario_path") or "")
    except (json.JSONDecodeError, OSError):
        return ""


def _descriptions(scenario_path: str) -> dict[str, str]:
    """対象物と品目の 名前 → 説明。run が使ったシナリオからだけ引く。"""
    if not scenario_path:
        return {}
    for base in (_REPO_ROOT, _REPO_ROOT.parent.parent.parent):
        p = base / scenario_path
        if p.exists():
            break
    else:
        return {}
    try:
        d = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, str] = {}
    for spot in d.get("spots", []):
        for obj in (spot.get("interior") or {}).get("objects", []):
            if obj.get("name"):
                out.setdefault(obj["name"], obj.get("description") or "")
    for spec in d.get("item_specs", []):
        if spec.get("name"):
            out.setdefault(spec["name"], spec.get("description") or "")
    return out


def _parse_candidates(raw: str) -> list[str]:
    raw = raw.strip()
    if "ありません" in raw or "なし" in raw:
        return []
    names = []
    for part in raw.split(" / "):
        part = part.strip()
        m = re.match(r"OBJ\d+ \((.+)\)$", part)
        if m:
            part = m.group(1)
        part = part.strip().strip('"')
        if part:
            names.append(part)
    return names


def extract_cases(runs_dir: Path) -> tuple[list[Case], dict[str, int]]:
    cases: list[Case] = []
    census = {"failures_total": 0, "darkness": 0, "without_candidates": 0, "unparsed": 0, "with_candidates": 0}
    for trace in sorted(runs_dir.glob("*/trace.jsonl")):
        scenario_path = _run_scenario(trace.parent)
        descriptions = _descriptions(scenario_path)
        events = _load_events(trace)
        for i, e in enumerate(events):
            p = e.get("payload") or {}
            if e.get("kind") != "action_result" or p.get("error_code") != "INVALID_TARGET_LABEL":
                continue
            if p.get("tool") not in _TOOLS:
                continue
            census["failures_total"] += 1
            msg = (p.get("result_summary") or p.get("message") or "").strip()
            if "暗くて見えない" in msg:
                census["darkness"] += 1
                continue
            written = None
            names: list[str] = []
            for pat in _PATTERNS:
                m = pat.search(msg)
                if m:
                    written = m.group("written").strip().strip('"')
                    names = _parse_candidates(m.group("cands"))
                    break
            if written is None:
                census["unparsed" if "候補" not in msg else "without_candidates"] += 1
                continue
            if not names or not written:
                census["without_candidates"] += 1
                continue
            census["with_candidates"] += 1
            args = _preceding_action(events, i).get("arguments") or {}
            cases.append(Case(
                run=trace.parent.name, tick=e.get("tick"), player_id=e.get("player_id"),
                tool=p["tool"], written=written,
                inner_thought=str(args.get("inner_thought") or ""),
                candidates={n: descriptions.get(n, "") for n in names},
                scenario_path=scenario_path,
            ))
    return cases, census


def build_controls(cases: Sequence[Case], seed: int = 20260922) -> list[Case]:
    rng = random.Random(seed)
    controls = []
    for case in cases:
        others = [c for c in cases if c.run != case.run and set(c.candidates) != set(case.candidates)]
        if not others:
            continue
        donor = rng.choice(others)
        controls.append(Case(
            run=case.run, tick=case.tick, player_id=case.player_id, tool=case.tool,
            written=case.written, inner_thought=case.inner_thought,
            candidates=dict(donor.candidates), scenario_path=donor.scenario_path,
            is_control=True, borrowed_from=donor.run,
        ))
    return controls


def judge_difflib(case: Case, cutoff: float = 0.6) -> Outcome:
    best, score = None, 0.0
    for name in case.candidates:
        s = SequenceMatcher(None, case.written, name).ratio()
        if s > score:
            best, score = name, s
    return Outcome("difflib", best if score >= cutoff else None, raw_choice=best, score=round(score, 3))


def judge_jev(case: Case, port: Any, min_confidence: float) -> Outcome:
    from ai_rpg_world.application.llm.ports.typed_judgment_port import (
        ChoiceQuestion,
        TypedJudgmentUnavailableException,
    )

    options: dict[str, str | None] = {n: (d or None) for n, d in case.candidates.items()}
    options[_NO_MATCH] = "一覧のどれにも当たらない"
    state: dict[str, Any] = {
        "written_target_name": case.written,
        "tool": case.tool,
        "candidates": {n: d for n, d in case.candidates.items() if d} or list(case.candidates),
    }
    if case.inner_thought:
        state["inner_thought"] = case.inner_thought
    question = ChoiceQuestion(
        instructions=(
            "書かれた対象の名前 written_target_name は、いま選べる候補のどれを指しているか。"
            f"どれでもなければ {_NO_MATCH} を選ぶ。"
        ),
        options=options,
    )
    try:
        answers = port.judge(state, {"target_label_rescue": question})
    except TypedJudgmentUnavailableException as exc:
        return Outcome("jev", None, error=str(exc))
    a = answers["target_label_rescue"]
    chosen = str(a.value)
    prob = a.probabilities.get(chosen)
    accepted = chosen != _NO_MATCH and chosen in case.candidates and prob is not None and prob >= min_confidence and (a.confidence is None or a.confidence >= min_confidence)
    return Outcome("jev", chosen if accepted else None, raw_choice=chosen, score=prob, confidence=a.confidence, latency_ms=round(a.latency_ms, 1))


def cmd_extract(args: argparse.Namespace) -> int:
    cases, census = extract_cases(Path(args.runs_dir))
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"census": census, "cases": [asdict(c) for c in cases]}, ensure_ascii=False, indent=1))
    print(json.dumps(census, ensure_ascii=False))
    print(f"cases: {len(cases)} → {out}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv
    load_dotenv(); load_dotenv(_REPO_ROOT.parent.parent.parent / ".env")
    from ai_rpg_world.application.llm.wiring._typed_judgment_factory import create_typed_judgment_port_from_config
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
    port = create_typed_judgment_port_from_config(ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="jev"))
    data = json.loads(Path(args.cases).read_text())
    cases = [Case(**c) for c in data["cases"]]
    controls = build_controls(cases)
    results = []
    for c in cases + controls:
        results.append({"case": asdict(c), "difflib": asdict(judge_difflib(c)), "jev": asdict(judge_jev(c, port, args.min_confidence))})
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"census": data["census"], "min_confidence": args.min_confidence, "results": results}, ensure_ascii=False, indent=1))
    real = [r for r in results if not r["case"]["is_control"]]
    ctrl = [r for r in results if r["case"]["is_control"]]
    print(f"\n事例 {len(real)} 件 / 対照 {len(ctrl)} 件 (閾値 {args.min_confidence})")
    for name, rows in (("事例", real), ("対照", ctrl)):
        jev_acc = sum(1 for r in rows if r["jev"]["chosen"]); jev_no = sum(1 for r in rows if r["jev"]["raw_choice"] == _NO_MATCH)
        dl = sum(1 for r in rows if r["difflib"]["chosen"])
        print(f"  {name}: jev 採用 {jev_acc}, 該当なし {jev_no}, 閾値未満 {len(rows)-jev_acc-jev_no} | difflib 採用 {dl}")
    print("\n=== 事例 (書かれた名前 → Jev の選択 [確率/確信] | 候補) ===")
    for r in real:
        c = r["case"]; j = r["jev"]
        mark = "採用" if j["chosen"] else ("該当なし" if j["raw_choice"] == _NO_MATCH else "閾値未満")
        print(f"[{c['tool']}] 「{c['written']}」 → {j['raw_choice']} ({j['score']}/{j['confidence']}) {mark} | 候補: {' / '.join(c['candidates'])}")
    print("\n=== 対照で何かを選んだもの (誤救済) ===")
    for r in ctrl:
        c = r["case"]; j = r["jev"]
        if j["chosen"]:
            print(f"[{c['tool']}] 「{c['written']}」 → {j['raw_choice']} ({j['score']}/{j['confidence']}) | 候補: {' / '.join(c['candidates'])}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pe = sub.add_parser("extract"); pe.add_argument("--runs-dir", required=True); pe.add_argument("--out", default="var/jev_label_demo/cases.json"); pe.set_defaults(func=cmd_extract)
    pr = sub.add_parser("run"); pr.add_argument("--cases", default="var/jev_label_demo/cases.json"); pr.add_argument("--out", default="var/jev_label_demo/results.json"); pr.add_argument("--min-confidence", type=float, default=0.7); pr.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
