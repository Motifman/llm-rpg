#!/usr/bin/env python3
"""Issue #1429 の失敗5件をJevが修復または正しく拒否できるか測る。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from ai_rpg_world.application.llm.ports.typed_judgment_port import ChoiceQuestion  # noqa: E402
from ai_rpg_world.infrastructure.llm.jev_typed_judgment_adapter import (  # noqa: E402
    JevTypedJudgmentAdapter,
)

NO_MATCH = "__no_match__"
FAILURE_CALLS = (
    ("issue_1429_gemma_baseline_004", "4e49dc8d-d7e7-4205-b0ec-19ea7898d97d", "target_label", "冷蔵庫"),
    ("issue_1429_deepseek_baseline_004", "abae3e77-7c77-4033-928a-3699e8b8f381", "destination_label", None),
    ("issue_1429_deepseek_baseline_004", "8727d865-6899-4f8d-a337-32f80f6e3896", "destination_label", None),
    ("issue_1429_deepseek_baseline_004", "58173022-2b4e-4b7c-9b29-4f9570aa543f", "destination_label", None),
    ("issue_1429_deepseek_baseline_004", "7ef69241-1cd9-47ee-84d4-87e0d26ddd2b", "target_label", None),
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _values(snapshot: dict[str, Any], tool: str, argument: str) -> list[str]:
    for entry in snapshot["entries"]:
        if entry.get("tool") == tool and entry.get("argument") == argument:
            return list(entry.get("values") or [])
    return []


def load_cases(runs_dir: Path) -> list[dict[str, Any]]:
    cases = []
    for run, call_id, argument, expected in FAILURE_CALLS:
        calls = {row["llm_call_id"]: row for row in _read_jsonl(runs_dir / run / "prompt_dataset" / "calls.jsonl")}
        call = calls[call_id]
        output = call["output"]
        tool = output["name"]
        args = output.get("arguments") or {}
        candidates = _values(call["dynamic_argument_candidates"], tool, argument)
        if not candidates:
            raise ValueError(f"{call_id}: {tool}.{argument} の候補がない")
        cases.append(
            {
                "run": run,
                "llm_call_id": call_id,
                "world_tick": call["world_tick"],
                "character_name": call["character_name"],
                "tool": tool,
                "argument": argument,
                "written": args.get(argument),
                "arguments": args,
                "inner_thought": args.get("inner_thought") or "",
                "candidates": candidates,
                "expected": expected,
            }
        )
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "var" / "runs")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--secret-env-file",
        type=Path,
        default=REPO_ROOT / ".env",
        help="APIキーを読む.env。値は成果物へ保存しない。",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-confidence", type=float, default=0.7)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"既存結果を上書きしない: {args.out}")

    cases = load_cases(args.runs_dir)
    if args.dry_run:
        print(json.dumps(cases, ensure_ascii=False, indent=2))
        return 0

    from dotenv import load_dotenv

    load_dotenv(args.secret_env_file)
    api_key = (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY または OPENROUTER_API_KEY がない")
    adapter = JevTypedJudgmentAdapter(
        api_key=api_key,
        endpoint="https://openrouter.ai/api/alpha/decisions",
        model="typesafe/jev-1.13",
        timeout_seconds=30,
        rate_limit_retry_attempts=3,
    )

    results = []
    for index, case in enumerate(cases, 1):
        options: dict[str, str | None] = {candidate: None for candidate in case["candidates"]}
        options[NO_MATCH] = "候補のどれも、元の意図した値に対応しない"
        question = ChoiceQuestion(
            instructions=(
                f"無効だった {case['tool']}.{case['argument']} を修復する。"
                "元の意図した値と同じ対象を指す候補を一つ選ぶ。"
                f"同じ対象が候補に無ければ、推測で別対象を選ばず {NO_MATCH} を選ぶ。"
            ),
            options=options,
        )
        answers = adapter.judge(
            {
                "tool": case["tool"],
                "argument": case["argument"],
                "written_value": case["written"],
                "original_arguments": case["arguments"],
                "inner_thought": case["inner_thought"],
                "candidates": case["candidates"],
            },
            {"repair": question},
        )
        answer = answers["repair"]
        raw = str(answer.value)
        probability = answer.probabilities.get(raw)
        accepted = (
            raw in case["candidates"]
            and probability is not None
            and probability >= args.min_confidence
            and (answer.confidence is None or answer.confidence >= args.min_confidence)
        )
        chosen = raw if accepted else None
        expected_raw = case["expected"] if case["expected"] is not None else NO_MATCH
        row = {
            **case,
            "raw_choice": raw,
            "chosen": chosen,
            "probability": probability,
            "confidence": answer.confidence,
            "latency_ms": round(answer.latency_ms, 1),
            "expected_raw_choice": expected_raw,
            "correct": raw == expected_raw,
            "repairable": case["expected"] is not None,
        }
        results.append(row)
        print(f"[{index}/{len(cases)}] {case['character_name']}: {raw} correct={row['correct']}", flush=True)

    payload = {
        "schema_version": 1,
        "model": "typesafe/jev-1.13",
        "min_confidence": args.min_confidence,
        "cases": results,
        "summary": {
            "total": len(results),
            "correct": sum(row["correct"] for row in results),
            "repairable": sum(row["repairable"] for row in results),
            "repaired": sum(row["repairable"] and row["chosen"] == row["expected"] for row in results),
            "should_refuse": sum(not row["repairable"] for row in results),
            "correctly_refused": sum(not row["repairable"] and row["raw_choice"] == NO_MATCH for row in results),
            "wrong_substitutions": sum(not row["repairable"] and row["raw_choice"] != NO_MATCH for row in results),
            "cost_usd": None,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
