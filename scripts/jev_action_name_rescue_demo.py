"""過去 run の「操作名が解決できなかった」失敗を、Jev が救えるかを実データで測る。

## 何を確かめるのか

エージェントは表示にある操作名をそのまま書けないことがある。引用符ごと写す、
表示行を丸ごと貼る、意味は同じだが自分の語彙で書く。engine 側は文字の一致
でしか解決できないので、これらは「その操作はありません」で失敗する。

意味で選び直せば救えるはずだが、**救いすぎると別の害が出る**。世界に無い行為を
「一番近い操作」に化けさせると、エージェントは自分が何をしたのか分からなくなる。

そこで 2 つを対で測る。

1. **救済率**: 実際に失敗した事例を、どれだけ正しい候補へ寄せられるか
2. **誤救済率**: 正解が存在しない事例で、どれだけ「該当なし」と言えるか

2 は入れ替え対照で作る。事例 A に書かれた操作名を、無関係な事例 B の候補一覧と
組み合わせる。ほとんどの組は正解を持たないので、ここで何かを選んでしまう割合が
そのまま誤救済率の上限になる。

## 比べる相手

- ``verbatim``: 生値がそのまま候補にあるか (= engine の現行判定)
- ``normalized``: 引用符剥がし等の表記の崩れの救済 (現行の ``_pick_action_name``)
- ``difflib``: 文字の類似度で最も近い候補に置き換える (閾値つき)
- ``jev``: 意味で選ぶ。「該当なし」を選択肢に含める

## 使い方

    # 1. 過去 run から事例を切り出す (API を呼ばない)
    uv run python scripts/jev_action_name_rescue_demo.py extract \\
        --runs-dir ../../var/runs --out var/jev_demo/cases.json

    # 2. 実際に Jev へ問う (課金あり。件数とコストは最後に出る)
    uv run python scripts/jev_action_name_rescue_demo.py run \\
        --cases var/jev_demo/cases.json --out var/jev_demo/results.json

    # 3. 人が読む HTML にする
    uv run python scripts/jev_action_name_rescue_demo.py report \\
        --results var/jev_demo/results.json --out var/jev_demo/report.html
"""

from __future__ import annotations

import argparse
import html
import json
import os
import random
import re
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
# ``scripts.build_run_index`` を直接実行でも import できるようにする。pytest は
# repo root を通すので、テストだけ緑で実行が落ちる形になっていた。
sys.path.insert(0, str(_REPO_ROOT))

#: 失敗文から「書かれた名前」と「利用可能な操作」を取り出す。
#:
#: 文面は engine が組み立てている。実データの 4 形式のうち、候補一覧を持つのは
#: object 形式だけで、残りは候補が空 (役割で伏せられている / 対人で候補なし)。
#: **候補が空の事例は救済の対象外なので、ここで落とす。**
_OBJECT_FAILURE = re.compile(
    r"このオブジェクトには\s*'(?P<written>.*?)'\s*という操作がありません。"
    r"利用可能な操作:\s*(?P<available>.+?)\s*$"
)


@dataclass
class Case:
    """1 件の失敗。state に使う値と、候補一覧を持つ。"""

    run: str
    tick: int | None
    player_id: int | None
    written: str
    target: str
    inner_thought: str
    available: list[str]
    #: この run が使ったシナリオ。意味ラベルを **その run の宣言から** 引く
    #: ために要る。全シナリオを舐めて引くと、同じ action_name に別のラベルを
    #: 付けている世界 (examine / read_board / drink_water) で取り違える。
    scenario_path: str = ""
    scenario_sha256: str = ""
    #: 入れ替え対照なら True。正解が存在しない前提で測る
    is_control: bool = False
    #: 入れ替え元 (対照の出所を追えるようにする)
    borrowed_from: str | None = None


@dataclass
class Outcome:
    """1 件の判定結果。手法ごとに 1 つ。"""

    method: str
    #: 採用した選択。閾値未満と「該当なし」はどちらも None
    chosen: str | None
    #: モデルが選んだ生の値 (``__no_match__`` を含む)。
    #:
    #: chosen だけだと「世界に無いと言えた」のか「自信が足りなかった」のかが
    #: 区別できない。**断れたことと迷ったことを同じ数にしない。**
    raw_choice: str | None = None
    score: float | None = None
    confidence: float | None = None
    latency_ms: float | None = None
    error: str | None = None


@dataclass
class CaseResult:
    case: Case
    outcomes: dict[str, Outcome] = field(default_factory=dict)


# ─────────────────────────────── extract ───────────────────────────────


def _load_events(path: Path) -> list[dict]:
    events: list[dict] = []
    with path.open() as handle:
        for line in handle:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _preceding_action(events: Sequence[dict], index: int) -> dict:
    """失敗の直前にある同じ人の action イベントを返す。無ければ空 dict。"""
    failure = events[index]
    for j in range(index - 1, max(-1, index - 8), -1):
        candidate = events[j]
        if candidate.get("kind") != "action":
            continue
        if candidate.get("player_id") != failure.get("player_id"):
            continue
        return candidate.get("payload") or {}
    return {}


def extract_cases(runs_dir: Path) -> tuple[list[Case], dict[str, int]]:
    """過去 run から、候補一覧を持つ失敗を切り出す。

    Returns:
        (事例, 母集団の内訳)。内訳は「何を落としたか」を数えるために返す。
        落とした数を出さないと、救済率の分母が何なのか読み手に分からない。
    """
    cases: list[Case] = []
    census = {
        "runs_scanned": 0,
        "failures_total": 0,
        "with_candidates": 0,
        "without_candidates": 0,
        "unparsed_message": 0,
        "no_preceding_action": 0,
    }
    for trace in sorted(runs_dir.glob("*/trace.jsonl")):
        census["runs_scanned"] += 1
        scenario_path, scenario_sha = _run_scenario(trace.parent)
        if not scenario_path:
            census["run_without_scenario"] = census.get("run_without_scenario", 0) + 1
        events = _load_events(trace)
        for index, event in enumerate(events):
            payload = event.get("payload") or {}
            if payload.get("error_code") != "INTERACTION_ACTION_NOT_FOUND":
                continue
            census["failures_total"] += 1
            message = payload.get("result_summary") or ""
            matched = _OBJECT_FAILURE.search(message)
            if matched is None:
                # 候補一覧を持たない形式 (役割で全操作が伏せられている等)。
                # 救済の対象外。
                if "利用可能な操作" in message:
                    census["unparsed_message"] += 1
                else:
                    census["without_candidates"] += 1
                continue
            available = [
                name.strip()
                for name in matched.group("available").split(",")
                if name.strip() and name.strip() != "(なし)"
            ]
            if not available:
                census["without_candidates"] += 1
                continue
            arguments = _preceding_action(events, index).get("arguments") or {}
            if not arguments:
                census["no_preceding_action"] += 1
            census["with_candidates"] += 1
            cases.append(
                Case(
                    run=trace.parent.name,
                    tick=event.get("tick"),
                    player_id=event.get("player_id"),
                    written=matched.group("written"),
                    target=str(arguments.get("object_label") or arguments.get("target_label") or ""),
                    inner_thought=str(arguments.get("inner_thought") or ""),
                    available=available,
                    scenario_path=scenario_path,
                    scenario_sha256=scenario_sha,
                )
            )
    return cases, census


def _run_scenario(run_dir: Path) -> tuple[str, str]:
    """run が使ったシナリオのパスと hash を、解決済み設定から引く。

    実験 runner が ``experiment.config.resolved.json`` に残している。無い run
    (手動実行など) は空文字を返し、呼び出し側が「引けなかった」と数える。
    """
    config = run_dir / "experiment.config.resolved.json"
    if not config.exists():
        return "", ""
    try:
        data = json.loads(config.read_text())
    except (json.JSONDecodeError, OSError):
        return "", ""
    return str(data.get("scenario_path") or ""), str(data.get("scenario_sha256") or "")


def build_controls(cases: Sequence[Case], seed: int = 20260920) -> list[Case]:
    """入れ替え対照を作る。

    事例 A の書かれた名前を、無関係な事例 B の候補一覧と組み合わせる。正解を
    持たない組がほとんどなので、ここで何かを選ぶ割合が誤救済率の上限になる。

    **書かれた名前が偶然 B の候補に在る組は捨てる。** 正解が在る組を対照に
    混ぜると、誤救済率が実際より高く出る。
    """
    rng = random.Random(seed)
    controls: list[Case] = []
    for case in cases:
        for _ in range(8):
            other = rng.choice(cases)
            if other.run == case.run or other.written == case.written:
                continue
            if case.written in other.available:
                continue
            if set(case.available) == set(other.available):
                continue
            controls.append(
                Case(
                    run=case.run,
                    tick=case.tick,
                    player_id=case.player_id,
                    written=case.written,
                    target=other.target,
                    inner_thought=case.inner_thought,
                    available=list(other.available),
                    # 候補を借りたのだから、ラベルの出所も借り元に合わせる。
                    scenario_path=other.scenario_path,
                    scenario_sha256=other.scenario_sha256,
                    is_control=True,
                    borrowed_from=other.run,
                )
            )
            break
    return controls


# ─────────────────────────────── methods ───────────────────────────────


def judge_verbatim(case: Case) -> Outcome:
    """生値がそのまま候補に在るか。engine の現行判定そのもの。"""
    chosen = case.written if case.written in case.available else None
    return Outcome(method="verbatim", chosen=chosen)


def judge_normalized(case: Case) -> Outcome:
    """表記の崩れ (引用符つき / 表示行の丸ごとコピー) を剥がしてから照合する。"""
    from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (  # noqa: E501
        normalize_action_name_candidates,
    )

    for candidate in normalize_action_name_candidates(case.written):
        if candidate in case.available:
            return Outcome(method="normalized", chosen=candidate)
    return Outcome(method="normalized", chosen=None)


def judge_difflib(case: Case, cutoff: float) -> Outcome:
    """文字の類似度が最も高い候補に置き換える。閾値未満なら選ばない。"""
    best_name: str | None = None
    best_score = 0.0
    for name in case.available:
        score = SequenceMatcher(None, case.written, name).ratio()
        if score > best_score:
            best_name, best_score = name, score
    if best_name is None or best_score < cutoff:
        return Outcome(method="difflib", chosen=None, score=round(best_score, 4))
    return Outcome(method="difflib", chosen=best_name, score=round(best_score, 4))


_NO_MATCH = "__no_match__"


def _labels_in(path: Path) -> dict[str, str]:
    """1 つのシナリオ宣言から ``action_name -> display_label`` を集める。"""
    labels: dict[str, str] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            name, label = node.get("action_name"), node.get("display_label")
            if isinstance(name, str) and isinstance(label, str) and label.strip():
                labels[name] = label.strip()
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    try:
        walk(json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        return {}
    return labels


class LabelBook:
    """意味ラベルを、**その run が使ったシナリオから** 引く。

    過去 run の trace には表示ラベルが載っていない。本番 (#1323 以降) はラベルを
    選択肢の説明として送るので、ラベル無しで測ると本番より弱い設定を測ることに
    なる。そこで宣言から引き直す。

    全シナリオを舐めて 1 つの辞書にすると、同じ ``action_name`` に別のラベルを
    付けている世界で取り違える (``examine`` は 4 通り、``read_board`` は 2 通り
    の表記がある)。**run ごとに引く。**
    """

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._per_scenario: dict[str, dict[str, str]] = {}
        self.hits = {"exact": 0, "missing_scenario": 0, "missing_label": 0}

    def for_case(self, case: Case) -> dict[str, str]:
        if not case.scenario_path:
            self.hits["missing_scenario"] += 1
            return {}
        if case.scenario_path not in self._per_scenario:
            path = self._repo_root / case.scenario_path
            self._per_scenario[case.scenario_path] = _labels_in(path) if path.exists() else {}
        labels = self._per_scenario[case.scenario_path]
        if not labels:
            self.hits["missing_scenario"] += 1
            return {}
        if any(name not in labels for name in case.available):
            self.hits["missing_label"] += 1
        else:
            self.hits["exact"] += 1
        return labels


#: 何が効いているかを切り分ける変種。
#:
#: ``full`` が本番と同じ形 (意味ラベルつき)。過去 run の trace にはラベルが
#: 無いので、``names_only`` が「デモの元データそのまま」になる。
VARIANTS = {
    "full": {"labels": True, "inner_thought": True, "target": True},
    "names_only": {"labels": False, "inner_thought": True, "target": True},
    "no_thought": {"labels": True, "inner_thought": False, "target": True},
    "no_target": {"labels": True, "inner_thought": True, "target": False},
    "bare": {"labels": False, "inner_thought": False, "target": False},
}


def judge_jev(
    case: Case,
    adapter: Any,
    min_confidence: float,
    *,
    labels: dict[str, str] | None = None,
    variant: str = "names_only",
) -> Outcome:
    """意味で選び直す。「該当なし」を選択肢に含める。"""
    from ai_rpg_world.application.llm.ports.typed_judgment_port import (
        ChoiceQuestion,
        TypedJudgmentUnavailableException,
    )

    config = VARIANTS[variant]
    known = labels or {}
    option_labels = {name: (known.get(name) if config["labels"] else None) for name in case.available}
    options: dict[str, str | None] = dict(option_labels)
    options[_NO_MATCH] = "一覧のどの操作とも対応しない"
    listed = {name: label for name, label in option_labels.items() if label}
    state: dict[str, Any] = {
        "written_action_name": case.written,
        "available_interactions": listed or list(case.available),
    }
    if config["target"] and case.target:
        state["target"] = case.target
    if config["inner_thought"] and case.inner_thought:
        state["inner_thought"] = case.inner_thought
    question = ChoiceQuestion(
        instructions=(
            "書かれた行動名 written_action_name は、対象が持つ操作のどれを"
            f"意図しているか。どれにも当たらなければ {_NO_MATCH} を選ぶ。"
        ),
        options=options,
    )
    try:
        answers = adapter.judge(state, {"action_name_rescue": question})
    except TypedJudgmentUnavailableException as exc:
        return Outcome(method="jev", chosen=None, error=str(exc))
    answer = answers["action_name_rescue"]
    chosen = str(answer.value)
    probability = answer.probabilities.get(chosen)
    accepted = (
        chosen != _NO_MATCH
        and chosen in case.available
        and probability is not None
        and probability >= min_confidence
        and (answer.confidence is None or answer.confidence >= min_confidence)
    )
    return Outcome(
        method="jev",
        chosen=chosen if accepted else None,
        raw_choice=chosen,
        score=probability,
        confidence=answer.confidence,
        latency_ms=round(answer.latency_ms, 1),
    )


# ─────────────────────────────── commands ───────────────────────────────


def _run_conditions(cases_path: Path, cases: Sequence[Case]) -> dict[str, Any]:
    """測定の条件を集める。

    **数字だけ残しても振り返れない。** どのコードで、どの入力に対して、どの
    設定で出した数字なのかが無いと、2 週間後に「71/99」の意味が復元できない。
    実験 runner が ``experiment.config.resolved.json`` に git 情報を残している
    のと同じ考えで、probe にも同じものを持たせる。
    """
    import hashlib
    import subprocess
    from datetime import datetime, timezone

    def _git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=_REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    digest = hashlib.sha256()
    for case in cases:
        digest.update(json.dumps(asdict(case), ensure_ascii=False, sort_keys=True).encode())
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "cases_path": str(cases_path),
        "cases_sha256": digest.hexdigest(),
        "cases_total": len(cases),
        "cases_real": sum(1 for c in cases if not c.is_control),
        "cases_control": sum(1 for c in cases if c.is_control),
    }


def _api_key() -> str:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # pragma: no cover - 依存が無い環境向け
        pass
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value and value != "EMPTY":
            return value
    return ""


def cmd_extract(args: argparse.Namespace) -> int:
    cases, census = extract_cases(Path(args.runs_dir))
    controls = build_controls(cases)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "census": census,
                "controls": len(controls),
                "cases": [asdict(c) for c in cases + controls],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(json.dumps(census, ensure_ascii=False, indent=2))
    print(f"実事例 {len(cases)} 件 / 入れ替え対照 {len(controls)} 件 -> {out}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from ai_rpg_world.infrastructure.llm.jev_typed_judgment_adapter import (
        JevTypedJudgmentAdapter,
    )

    payload = json.loads(Path(args.cases).read_text())
    cases = [Case(**c) for c in payload["cases"]]
    if args.limit:
        cases = cases[: args.limit]

    api_key = _api_key()
    if not api_key:
        print("OPENROUTER_API_KEY / OPENAI_API_KEY が無い", file=sys.stderr)
        return 2
    adapter = JevTypedJudgmentAdapter(
        api_key=api_key,
        endpoint=args.endpoint,
        model=args.model,
        timeout_seconds=30.0,
        rate_limit_retry_attempts=3,
    )

    labels = LabelBook(Path(args.repo_root)) if args.repo_root else None
    results: list[CaseResult] = []
    started = time.perf_counter()
    for index, case in enumerate(cases, start=1):
        result = CaseResult(case=case)
        result.outcomes["verbatim"] = judge_verbatim(case)
        result.outcomes["normalized"] = judge_normalized(case)
        result.outcomes["difflib"] = judge_difflib(case, cutoff=args.difflib_cutoff)
        result.outcomes["jev"] = judge_jev(
            case,
            adapter,
            args.min_confidence,
            labels=(labels.for_case(case) if labels else None),
            variant=args.variant,
        )
        results.append(result)
        if index % 20 == 0 or index == len(cases):
            print(f"  {index}/{len(cases)} 件", file=sys.stderr)
    elapsed = time.perf_counter() - started

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "conditions": _run_conditions(Path(args.cases), cases),
                "census": payload.get("census"),
                "model": args.model,
                "endpoint": args.endpoint,
                "min_confidence": args.min_confidence,
                "variant": args.variant,
                "label_lookup": (labels.hits if labels else None),
                "difflib_cutoff": args.difflib_cutoff,
                "elapsed_seconds": round(elapsed, 1),
                "results": [
                    {"case": asdict(r.case), "outcomes": {k: asdict(v) for k, v in r.outcomes.items()}} for r in results
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"{len(results)} 件を {elapsed:.1f}s で判定 -> {out}")
    return 0


def summarize(results: Sequence[dict], methods: Sequence[str]) -> dict[str, Any]:
    """手法ごとに、実事例の救済率と対照の誤救済率を出す。"""
    real = [r for r in results if not r["case"]["is_control"]]
    control = [r for r in results if r["case"]["is_control"]]
    summary: dict[str, Any] = {
        "real_total": len(real),
        "control_total": len(control),
        "methods": {},
    }
    for method in methods:
        rescued = sum(1 for r in real if r["outcomes"][method]["chosen"])
        wrong = sum(1 for r in control if r["outcomes"][method]["chosen"])
        errors = sum(1 for r in results if r["outcomes"][method].get("error"))
        stats = {
            "rescued": rescued,
            "rescue_rate": (rescued / len(real)) if real else None,
            "false_rescue": wrong,
            "false_rescue_rate": (wrong / len(control)) if control else None,
            "errors": errors,
        }
        if method == "jev":
            # 「該当なし」と言えた数と、選びかけたが閾値に届かなかった数を
            # 分ける。同じ「救済しなかった」でも意味が違う。
            stats["real_said_no_match"] = sum(1 for r in real if r["outcomes"][method].get("raw_choice") == _NO_MATCH)
            stats["real_below_threshold"] = sum(
                1
                for r in real
                if not r["outcomes"][method]["chosen"]
                and r["outcomes"][method].get("raw_choice") not in (None, _NO_MATCH)
            )
            stats["control_said_no_match"] = sum(
                1 for r in control if r["outcomes"][method].get("raw_choice") == _NO_MATCH
            )
            stats["control_below_threshold"] = sum(
                1
                for r in control
                if not r["outcomes"][method]["chosen"]
                and r["outcomes"][method].get("raw_choice") not in (None, _NO_MATCH)
            )
        summary["methods"][method] = stats
    # 母集団の偏りを出す。合計だけを見ると、件数の多い 1 つの名前の扱いが
    # そのまま「救済率」として読まれてしまう。
    from collections import Counter

    by_written: dict[str, dict[str, int]] = {}
    for item in real:
        bucket = by_written.setdefault(item["case"]["written"], {"total": 0, "jev": 0, "difflib": 0})
        bucket["total"] += 1
        if item["outcomes"]["jev"]["chosen"]:
            bucket["jev"] += 1
        if item["outcomes"]["difflib"]["chosen"]:
            bucket["difflib"] += 1
    summary["by_written"] = dict(sorted(by_written.items(), key=lambda kv: -kv[1]["total"]))

    by_option_count: dict[str, dict[str, int]] = {}
    for item in real:
        key = str(len(item["case"]["available"]))
        bucket = by_option_count.setdefault(key, {"total": 0, "jev": 0})
        bucket["total"] += 1
        if item["outcomes"]["jev"]["chosen"]:
            bucket["jev"] += 1
    for item in control:
        key = str(len(item["case"]["available"]))
        bucket = by_option_count.setdefault(key, {"total": 0, "jev": 0})
        bucket.setdefault("control_total", 0)
        bucket.setdefault("control_wrong", 0)
        bucket["control_total"] += 1
        if item["outcomes"]["jev"]["chosen"]:
            bucket["control_wrong"] += 1
    summary["by_option_count"] = dict(sorted(by_option_count.items()))

    latencies = [r["outcomes"]["jev"]["latency_ms"] for r in results if r["outcomes"]["jev"].get("latency_ms")]
    if latencies:
        ordered = sorted(latencies)
        summary["jev_latency_ms"] = {
            "p50": ordered[len(ordered) // 2],
            "p90": ordered[int(len(ordered) * 0.9)],
            "max": ordered[-1],
        }
    return summary


_METHODS = ("verbatim", "normalized", "difflib", "jev")


def load_labels(path: str | None) -> dict[str, dict[str, str]]:
    """対照で選ばれた組に人が付けたラベルを読む。

    入れ替え対照は「正解を持たない組」を作るつもりだが、``examine`` のような
    一般的な動詞はどの対象にも意味が通ってしまう。つまり対照の一部は正解が
    在る組になる。**その汚染を数えずに誤救済率と呼ばない。**
    """
    if not path:
        return {}
    data = json.loads(Path(path).read_text())
    return data.get("labels", {})


def apply_labels(
    summary: dict[str, Any],
    results: Sequence[dict],
    labels: dict[str, dict[str, str]],
) -> None:
    """ラベルで対照を仕分け、誤救済率を補正した値を足す。"""
    if not labels:
        return
    control = [r for r in results if r["case"]["is_control"]]
    picked = [r for r in control if r["outcomes"]["jev"]["chosen"]]
    verdicts = {"plausible": 0, "wrong": 0, "unlabelled": 0}
    unlabelled: list[str] = []
    for item in picked:
        key = f"{item['case']['written']}|{item['outcomes']['jev']['chosen']}"
        label = labels.get(key)
        if label is None:
            verdicts["unlabelled"] += 1
            unlabelled.append(key)
        else:
            verdicts[label["verdict"]] = verdicts.get(label["verdict"], 0) + 1
    summary["control_labelled"] = {
        "picked": len(picked),
        **verdicts,
        "unlabelled_keys": sorted(set(unlabelled)),
        # 「意味が通る組」は対照として不適切だったので、分母からも外す。
        "corrected_false_rescue_rate": (
            verdicts["wrong"] / (len(control) - verdicts["plausible"])
            if (len(control) - verdicts["plausible"]) > 0
            else None
        ),
    }


def index_row(payload: dict, summary: dict, out: Path) -> dict[str, Any]:
    """probe の結果を、run の索引と同じ形の 1 行にする。

    kind が違うだけで、引くための列は run と揃える。揃えないと、同じ索引に
    載せても横断で引けない。
    """
    conditions = payload.get("conditions") or {}
    measured_at = conditions.get("measured_at") or ""
    return {
        "kind": "probe",
        "id": f"jev_action_name_rescue_{measured_at[:19]}",
        "measured_at": measured_at,
        "conditions_recoverable": bool(conditions.get("git_commit")),
        "git_commit": conditions.get("git_commit"),
        "git_dirty": conditions.get("git_dirty"),
        "profile": None,
        "scenario": None,
        "scenario_sha256": None,
        "max_world_ticks": None,
        "model": payload.get("model"),
        "typed_judgment_provider": "jev",
        "metrics": {
            "variant": payload.get("variant"),
            "min_confidence": payload.get("min_confidence"),
            "cases_sha256": conditions.get("cases_sha256"),
            "real_total": summary.get("real_total"),
            "control_total": summary.get("control_total"),
            "rescued": summary["methods"]["jev"]["rescued"],
            "false_rescue_raw": summary["methods"]["jev"]["false_rescue"],
            "false_rescue_labelled_wrong": (summary.get("control_labelled", {}).get("wrong")),
            "difflib_rescued": summary["methods"]["difflib"]["rescued"],
            "normalized_rescued": summary["methods"]["normalized"]["rescued"],
            "label_lookup": payload.get("label_lookup"),
        },
        "artifacts": str(out.parent),
    }


def cmd_report(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.results).read_text())
    results = payload["results"]
    summary = summarize(results, _METHODS)
    apply_labels(summary, results, load_labels(args.labels))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_html(payload, summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"-> {out}")
    if args.index and payload.get("conditions"):
        from scripts.build_run_index import write_index

        row = index_row(payload, summary, out)
        write_index(Path(args.index), [row], merge=True)
        print(f"索引に 1 行追記 -> {args.index} (id={row['id']})")
    elif args.index:
        # 条件の無い古い結果は索引に載せない。載せると「いつ・どの commit で」
        # が空の行が並び、索引の意味が薄まる。
        print("測定条件が無いので索引に載せない (run を取り直すと入る)")
    return 0


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _render_html(payload: dict, summary: dict) -> str:
    rows = []
    for item in payload["results"]:
        case = item["case"]
        outcomes = item["outcomes"]
        jev = outcomes["jev"]
        rows.append(
            "<tr class='{cls}'>"
            "<td>{kind}</td><td>{run}</td><td class='mono'>{written}</td>"
            "<td>{target}</td><td class='mono'>{available}</td>"
            "<td class='mono'>{normalized}</td>"
            "<td class='mono'>{difflib} <span class='dim'>{dscore}</span></td>"
            "<td class='mono strong'>{jev} <span class='dim'>{jscore}</span></td>"
            "<td class='thought'>{thought}</td>"
            "</tr>".format(
                cls="control" if case["is_control"] else "real",
                kind="対照" if case["is_control"] else "実事例",
                run=html.escape(case["run"]),
                written=html.escape(case["written"]),
                target=html.escape(case["target"] or "—"),
                available=html.escape(", ".join(case["available"])),
                normalized=html.escape(outcomes["normalized"]["chosen"] or "—"),
                difflib=html.escape(outcomes["difflib"]["chosen"] or "—"),
                dscore=outcomes["difflib"].get("score") or "",
                jev=html.escape(jev["chosen"] or "—"),
                jscore=jev.get("score") or "",
                thought=html.escape((case["inner_thought"] or "")[:120]),
            )
        )

    method_rows = "".join(
        "<tr><td class='mono'>{m}</td><td>{rescued}</td><td>{rate}</td><td>{wrong}</td><td>{wrate}</td></tr>".format(
            m=method,
            rescued=stats["rescued"],
            rate=_pct(stats["rescue_rate"]),
            wrong=stats["false_rescue"],
            wrate=_pct(stats["false_rescue_rate"]),
        )
        for method, stats in summary["methods"].items()
    )
    census = payload.get("census") or {}
    by_written = html.escape(json.dumps(summary.get("by_written", {}), ensure_ascii=False, indent=2))
    labelled = html.escape(json.dumps(summary.get("control_labelled", {}), ensure_ascii=False, indent=2))
    by_option_count = html.escape(json.dumps(summary.get("by_option_count", {}), ensure_ascii=False, indent=2))
    latency = summary.get("jev_latency_ms") or {}
    return f"""<!doctype html>
<meta charset="utf-8">
<title>操作名の救済: 過去 run の実データで測る</title>
<style>
 body {{ font-family: -apple-system, "Hiragino Sans", sans-serif; margin: 2rem; color: #1b1b1b; }}
 h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
 table {{ border-collapse: collapse; font-size: 0.82rem; width: 100%; }}
 th, td {{ border: 1px solid #ddd; padding: 4px 7px; vertical-align: top; }}
 th {{ background: #f3f3f3; text-align: left; position: sticky; top: 0; }}
 .mono {{ font-family: ui-monospace, Menlo, monospace; }}
 .strong {{ font-weight: 600; }}
 .dim {{ color: #888; font-size: 0.75rem; }}
 .control td {{ background: #fbf7ef; }}
 .thought {{ max-width: 24rem; color: #555; }}
 .note {{ background: #f6f8fa; padding: 0.8rem 1rem; border-left: 3px solid #999; }}
</style>
<h1>操作名の救済: 過去 run の実データで測る</h1>
<p class="note">
 <b>実事例</b>は過去 run で実際に <code>INTERACTION_ACTION_NOT_FOUND</code> になった呼び出し。
 <b>対照</b>は、その名前を無関係な run の候補一覧と組み合わせたもの。
 対照はほとんどが正解を持たないので、<b>ここで何かを選んだ割合が誤救済率の上限</b>になる。
</p>
<h2>母集団</h2>
<pre class="mono">{html.escape(json.dumps(census, ensure_ascii=False, indent=2))}</pre>
<h2>母集団の偏り</h2>
<p class="note">
 合計だけを見ると、件数の多い 1 つの名前の扱いがそのまま「救済率」として読まれる。
 書かれた名前ごと・候補数ごとの内訳を先に見ること。
</p>
<pre class="mono">{by_written}</pre>
<pre class="mono">{by_option_count}</pre>
<h2>対照の汚染 (人手ラベル)</h2>
<p class="note">
 入れ替え対照は「正解を持たない組」を作るつもりだが、<code>examine</code> のような
 一般的な動詞はどの対象にも意味が通ってしまう。選ばれた組を人が読んで分類した。
 <b>ラベルは正解データではなく判断である。</b>
</p>
<pre class="mono">{labelled}</pre>
<h2>手法ごとの結果</h2>
<table>
 <tr><th>手法</th><th>救済 (実事例)</th><th>救済率</th><th>誤救済 (対照)</th><th>誤救済率</th></tr>
 {method_rows}
</table>
<p>
 model: <code>{html.escape(payload.get("model", ""))}</code> /
 閾値: {payload.get("min_confidence")} /
 difflib cutoff: {payload.get("difflib_cutoff")} /
 latency p50 {latency.get("p50", "—")}ms · p90 {latency.get("p90", "—")}ms ·
 max {latency.get("max", "—")}ms /
 所要 {payload.get("elapsed_seconds")}s
</p>
<h2>全件</h2>
<table>
 <tr><th>種別</th><th>run</th><th>書かれた名前</th><th>対象</th><th>候補</th>
     <th>正規化</th><th>difflib</th><th>Jev</th><th>直前の思考</th></tr>
 {"".join(rows)}
</table>
"""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract", help="過去 run から事例を切り出す")
    p_extract.add_argument("--runs-dir", required=True)
    p_extract.add_argument("--out", default="var/jev_demo/cases.json")
    p_extract.set_defaults(func=cmd_extract)

    p_run = sub.add_parser("run", help="Jev と比較手法で判定する (課金あり)")
    p_run.add_argument("--cases", default="var/jev_demo/cases.json")
    p_run.add_argument("--out", default="var/jev_demo/results.json")
    p_run.add_argument("--limit", type=int, default=0)
    p_run.add_argument("--model", default="typesafe/jev-1.13")
    p_run.add_argument("--endpoint", default="https://openrouter.ai/api/alpha/decisions")
    p_run.add_argument("--min-confidence", type=float, default=0.7)
    p_run.add_argument("--difflib-cutoff", type=float, default=0.6)
    p_run.add_argument(
        "--variant",
        default="names_only",
        choices=sorted(VARIANTS),
        help="state と選択肢から何を落とすか。full が本番と同じ形",
    )
    p_run.add_argument(
        "--repo-root",
        default="",
        help=(
            "シナリオを引く起点。run の resolved config が持つ scenario_path をここから解決する。variant=full に要る"
        ),
    )
    p_run.set_defaults(func=cmd_run)

    p_report = sub.add_parser("report", help="HTML にする")
    p_report.add_argument("--results", default="var/jev_demo/results.json")
    p_report.add_argument("--out", default="var/jev_demo/report.html")
    p_report.add_argument(
        "--index",
        default="docs/experiments/run_index.jsonl",
        help="結果を 1 行追記する索引。空文字で無効",
    )
    p_report.add_argument(
        "--labels",
        default=str(Path(__file__).with_name("jev_rescue_control_labels.json")),
        help="対照で選ばれた組の人手ラベル。空文字で無効",
    )
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
