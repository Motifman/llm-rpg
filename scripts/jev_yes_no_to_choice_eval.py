"""はい / いいえの問いを「判断できない」入りの選択肢に変えてよいかを、実 Jev で比べる (#1427)。

memo の完了の判定と意味上の繰り返し (#233) を、今の ``NoulQuestion`` と選択肢の
``ChoiceQuestion`` の両方で同じ state に問い、採否を突き合わせる。2 つの形は同じ
リクエストに入れる。同じ state を送り直さないためで、質問は並列に評価される。

採否の基準:

- はい / いいえ: 確率が今の既定の閾値以上 (memo 0.7、繰り返し 0.8)
- 選択肢: ``fulfilled`` / ``repeating`` がいちばん確率の高い選択肢

母集団:

- ``labeled``: ``scripts/jev_semantic_repeat_demo.py`` のラベル付き 20 窓
- ``observed``: 観察 run の ``TYPED_JUDGMENT`` (``question=semantic_repeat``)。payload の
  ``window`` が当時渡した材料そのもの
- ``memo``: 観察 run の ``TYPED_JUDGMENT`` (``question=memo_completed``)。trace には memo の
  ID しか無いので、memo 本文は ``memo_add``、行動は同じ player の直前の ``action``、結果は
  直後の ``action_result`` から組み直す。1 回の問い合わせで問うた memo は、tick と player と
  tool が同じで seq が連続する記録の束として読む

使い方:
    uv run python scripts/jev_yes_no_to_choice_eval.py --part all --out var/jev_yes_no_to_choice/results.json
    uv run python scripts/jev_yes_no_to_choice_eval.py --part memo --port stub
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from jev_semantic_repeat_demo import CASES, _player_name, load_window  # noqa: E402

from ai_rpg_world.application.llm.ports.typed_judgment_port import (  # noqa: E402
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    NoulQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.action_summary_format import (  # noqa: E402
    format_action_summary_for_display,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (  # noqa: E402
    ResolvedLlmRuntimeConfig,
)

_DEFAULT_RUNS_DIR = _REPO_ROOT.parent.parent.parent / "var" / "runs"
_OBSERVED_REPEAT_RUN = "station_drill_gemma31_loop_jev_001"
_MEMO_RUNS = ("station_drill_gemma31_jev_001", "station_drill_gemma31_loop_jev_001")

#: 今の形の既定の閾値。比べる相手として固定する。
_NOUL_REPEAT_THRESHOLD = 0.8
_NOUL_MEMO_THRESHOLD = 0.7

_CANNOT_TELL = "cannot_tell"


# --- 今の形 (はい / いいえ)。src から消えても比べ直せるよう、文面をここに写す ---

def noul_repeat_question(actor: str) -> NoulQuestion:
    return NoulQuestion(
        instructions=_repeat_instructions(actor),
        true_means=_REPEATING_MEANS,
        false_means=_PROGRESSING_MEANS,
    )


def noul_memo_question(memo_content: str) -> NoulQuestion:
    return NoulQuestion(
        instructions=_memo_instructions(memo_content),
        true_means="果たされた",
        false_means="まだ果たされていない",
    )


# --- 選択肢の形 ---

def choice_repeat_question(actor: str) -> ChoiceQuestion:
    return ChoiceQuestion(
        instructions=_repeat_instructions(actor),
        options={
            "repeating": _REPEATING_MEANS,
            "progressing": _PROGRESSING_MEANS,
            _CANNOT_TELL: "行動と結果の文からは、同じことを繰り返しているかを判断できない",
        },
    )


def choice_memo_question(memo_content: str) -> ChoiceQuestion:
    return ChoiceQuestion(
        instructions=_memo_instructions(memo_content),
        options={
            "fulfilled": "この行動と結果で、memo に書いた意図が果たされた",
            "not_yet": (
                "memo の意図はまだ果たされていない。行動が memo と関係しない場合や、"
                "途中までしか進んでいない場合も含む"
            ),
            _CANNOT_TELL: "行動と結果の文からは、memo の意図が果たされたかを判断できない",
        },
    )


def _repeat_instructions(actor: str) -> str:
    return (
        f"{actor}は、直近のこれらの行動で、手段を変えずに同じことを試し続けているか。"
        "行動は古い順に並んでいる。"
    )


_REPEATING_MEANS = (
    "言い回し、呼び名、操作の名前が違っても、同じ相手や同じ対象に向けた同じ"
    "試みを繰り返していて、結果が同じまま変わっていない。同じ理由で拒否され"
    "続けている場合や、2 つの行動を行き来しているだけで状況が進んでいない場合も含む"
)
_PROGRESSING_MEANS = (
    "行動ごとに対象、相手、手段のどれかが変わっている。または前の結果を"
    "受けて次の段階へ進んでいる"
)


def _memo_instructions(memo_content: str) -> str:
    return f"この行動と結果で、memo「{memo_content}」の意図は果たされたか。"


def _choice_view(answer: JudgmentResult) -> dict[str, Any]:
    probabilities = {k: round(v, 4) for k, v in answer.probabilities.items()}
    top = max(probabilities, key=probabilities.__getitem__) if probabilities else None
    return {
        "chosen": str(answer.value),
        "top": top,
        "probabilities": probabilities,
        "confidence": answer.confidence,
    }


def _ask(
    port: ITypedJudgmentPort,
    state: Mapping[str, Any],
    questions: Mapping[str, NoulQuestion | ChoiceQuestion],
) -> Mapping[str, JudgmentResult] | str:
    try:
        return port.judge(state, questions)
    except TypedJudgmentUnavailableException as exc:
        return getattr(exc, "error_code", None) or "UNAVAILABLE"


# --- 意味上の繰り返し ---

def _judge_window(port: ITypedJudgmentPort, actor: str, state: Mapping[str, Any]) -> dict[str, Any]:
    answers = _ask(port, state, {"noul": noul_repeat_question(actor), "choice": choice_repeat_question(actor)})
    if isinstance(answers, str):
        return {"error": answers}
    choice = _choice_view(answers["choice"])
    noul = round(float(answers["noul"].value), 4)
    return {
        "noul": noul,
        "noul_accepted": noul >= _NOUL_REPEAT_THRESHOLD,
        "choice": choice,
        "choice_accepted": choice["top"] == "repeating",
    }


def run_labeled(port: ITypedJudgmentPort, runs_dir: Path, k: int, repeat: int) -> list[dict[str, Any]]:
    rows = []
    for case in CASES:
        name, actions, ticks = load_window(runs_dir, case.run, case.player_id, case.end_tick, k)
        state = {"actor": name, "recent_actions": [a.as_state() for a in actions]}
        samples = [_judge_window(port, name, state) for _ in range(repeat)]
        rows.append({
            "run": case.run, "player_id": case.player_id, "ticks": ticks,
            "repeating": case.repeating, "note": case.note, "state": state, "samples": samples,
        })
        print(
            f"{'繰り返し' if case.repeating else '非繰返し'} "
            f"noul={[s.get('noul') for s in samples]} "
            f"choice={[_short(s) for s in samples]} {case.run} p{case.player_id} {case.note}"
        )
    return rows


def run_observed(port: ITypedJudgmentPort, runs_dir: Path) -> list[dict[str, Any]]:
    run_dir = runs_dir / _OBSERVED_REPEAT_RUN
    rows = []
    for event in _events(run_dir):
        payload = event.get("payload") or {}
        if event.get("kind") != "typed_judgment" or payload.get("question") != "semantic_repeat":
            continue
        name = _player_name(run_dir, int(event["player_id"]))
        state = {"actor": name, "recent_actions": payload.get("window") or []}
        judged = _judge_window(port, name, state)
        rows.append({
            "seq": event.get("seq"), "tick": event.get("tick"), "player_id": event.get("player_id"),
            "actor": name, "recorded_probability": payload.get("probability"),
            "exact_match_fired": payload.get("exact_match_fired"), "state": state, **judged,
        })
        print(
            f"t{event.get('tick')} p{event.get('player_id')} 記録={payload.get('probability')} "
            f"noul={judged.get('noul')} choice={_short(judged)}"
        )
    return rows


# --- memo の完了 ---

def reconstruct_memo_calls(run_dir: Path) -> list[dict[str, Any]]:
    """trace から、memo の判定 1 回ぶんの材料を組み直す。"""
    events = _events(run_dir)
    memo_content: dict[str, str] = {}
    last_action: dict[int, dict[str, Any]] = {}
    calls: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for index, event in enumerate(events):
        kind = event.get("kind")
        payload = event.get("payload") or {}
        player_id = event.get("player_id")
        if kind == "memo_add":
            memo_content[str(payload.get("memo_id"))] = str(payload.get("content") or "").strip()
        if kind == "action" and player_id is not None:
            last_action[int(player_id)] = event
        is_memo_judgment = kind == "typed_judgment" and payload.get("question") == "memo_completed"
        if not is_memo_judgment:
            current = None
            continue
        key = (event.get("tick"), player_id, payload.get("tool_name"))
        if current is None or current["key"] != key:
            action_event = last_action.get(int(player_id))
            action_payload = (action_event or {}).get("payload") or {}
            current = {
                "key": key,
                "run": run_dir.name,
                "tick": event.get("tick"),
                "player_id": player_id,
                "tool_name": payload.get("tool_name"),
                "action_tool_matches": action_payload.get("tool") == payload.get("tool_name"),
                "action": format_action_summary_for_display(
                    str(action_payload.get("tool") or ""), action_payload.get("arguments") or {}
                ),
                "result": _next_result(events, index, player_id),
                "memos": [],
            }
            calls.append(current)
        memo_id = str(payload.get("memo_id"))
        current["memos"].append({
            "memo_id": memo_id,
            "content": memo_content.get(memo_id),
            "recorded_probability": payload.get("probability"),
        })
    for call in calls:
        call.pop("key", None)
    return calls


def _next_result(events: Sequence[Mapping[str, Any]], start: int, player_id: Any) -> str | None:
    for event in events[start:]:
        if event.get("kind") == "action_result" and event.get("player_id") == player_id:
            return str((event.get("payload") or {}).get("result_summary") or "")
    return None


def run_memo(port: ITypedJudgmentPort, runs_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for run in _MEMO_RUNS:
        for call in reconstruct_memo_calls(runs_dir / run):
            state = {"action": call["action"], "result": call["result"]}
            questions: dict[str, NoulQuestion | ChoiceQuestion] = {}
            for index, memo in enumerate(call["memos"]):
                content = memo["content"] or ""
                questions[f"noul_{index}"] = noul_memo_question(content)
                questions[f"choice_{index}"] = choice_memo_question(content)
            answers = _ask(port, state, questions)
            for index, memo in enumerate(call["memos"]):
                if isinstance(answers, str):
                    memo["error"] = answers
                    continue
                noul = round(float(answers[f"noul_{index}"].value), 4)
                choice = _choice_view(answers[f"choice_{index}"])
                memo.update({
                    "noul": noul,
                    "noul_accepted": noul >= _NOUL_MEMO_THRESHOLD,
                    "choice": choice,
                    "choice_accepted": choice["top"] == "fulfilled",
                })
                print(
                    f"{run} t{call['tick']} p{call['player_id']} 記録={memo['recorded_probability']} "
                    f"noul={noul} choice={_short(memo)} memo={(memo['content'] or '')[:30]!r} "
                    f"行動={call['action'][:30]!r}"
                )
            rows.append({**call, "state": state})
    return rows


# --- 共通 ---

def _events(run_dir: Path) -> list[dict[str, Any]]:
    out = []
    for line in (run_dir / "trace.jsonl").open():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _short(judged: Mapping[str, Any]) -> str:
    choice = judged.get("choice")
    if not choice:
        return str(judged.get("error"))
    top = choice["top"]
    return f"{top}:{choice['probabilities'].get(top)}"


def summarize(results: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    labeled = results.get("labeled")
    if labeled is not None:
        def counts(repeating: bool) -> dict[str, Any]:
            rows = [r for r in labeled if r["repeating"] is repeating]
            return {
                "cases": len(rows),
                "noul_accepted_any_sample": sum(any(s.get("noul_accepted") for s in r["samples"]) for r in rows),
                "noul_accepted_all_samples": sum(all(s.get("noul_accepted") for s in r["samples"]) for r in rows),
                "choice_accepted_any_sample": sum(any(s.get("choice_accepted") for s in r["samples"]) for r in rows),
                "choice_accepted_all_samples": sum(all(s.get("choice_accepted") for s in r["samples"]) for r in rows),
                "choice_cannot_tell_any_sample": sum(
                    any((s.get("choice") or {}).get("top") == _CANNOT_TELL for s in r["samples"]) for r in rows
                ),
            }
        summary["labeled"] = {"repeating": counts(True), "not_repeating": counts(False)}
    observed = results.get("observed")
    if observed is not None:
        ok = [r for r in observed if "choice" in r]
        summary["observed"] = {
            "judged": len(ok),
            "errors": len(observed) - len(ok),
            "recorded_noul_accepted": sum(1 for r in observed if (r["recorded_probability"] or 0) >= _NOUL_REPEAT_THRESHOLD),
            "noul_accepted": sum(1 for r in ok if r["noul_accepted"]),
            "choice_accepted": sum(1 for r in ok if r["choice_accepted"]),
            "choice_cannot_tell": sum(1 for r in ok if r["choice"]["top"] == _CANNOT_TELL),
        }
    memo = results.get("memo")
    if memo is not None:
        memos = [m for call in memo for m in call["memos"]]
        ok = [m for m in memos if "choice" in m]
        summary["memo"] = {
            "calls": len(memo),
            "judgments": len(memos),
            "errors": len(memos) - len(ok),
            "recorded_noul_accepted": sum(1 for m in memos if (m["recorded_probability"] or 0) >= _NOUL_MEMO_THRESHOLD),
            "noul_accepted": sum(1 for m in ok if m["noul_accepted"]),
            "choice_accepted": sum(1 for m in ok if m["choice_accepted"]),
            "choice_cannot_tell": sum(1 for m in ok if m["choice"]["top"] == _CANNOT_TELL),
            "disagreements": sum(1 for m in ok if m["noul_accepted"] != m["choice_accepted"]),
        }
    return summary


def _port(kind: str) -> ITypedJudgmentPort:
    if kind == "stub":
        from ai_rpg_world.application.llm.services.typed_judgment_stub import (
            DeterministicTypedJudgmentPort,
        )
        return DeterministicTypedJudgmentPort()
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(_REPO_ROOT.parent.parent.parent / ".env")
    from ai_rpg_world.application.llm.wiring._typed_judgment_factory import (
        create_typed_judgment_port_from_config,
    )
    port = create_typed_judgment_port_from_config(
        ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="jev")
    )
    assert port is not None
    return port


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", default=str(_DEFAULT_RUNS_DIR))
    parser.add_argument("--part", choices=("labeled", "observed", "memo", "all"), default="all")
    parser.add_argument("--port", choices=("jev", "stub"), default="jev")
    parser.add_argument("--repeat", type=int, default=2, help="labeled の窓を何回問うか")
    parser.add_argument("--k", type=int, default=ResolvedLlmRuntimeConfig.for_tests().typed_judgment_semantic_repeat_window)
    parser.add_argument("--out", default="var/jev_yes_no_to_choice/results.json")
    args = parser.parse_args(argv)
    runs_dir = Path(args.runs_dir)
    port = _port(args.port)
    results: dict[str, Any] = {"port": args.port}
    if args.part in ("labeled", "all"):
        results["labeled"] = run_labeled(port, runs_dir, args.k, args.repeat)
    if args.part in ("observed", "all"):
        results["observed"] = run_observed(port, runs_dir)
    if args.part in ("memo", "all"):
        results["memo"] = run_memo(port, runs_dir)
    results["summary"] = summarize(results)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(json.dumps(results["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
