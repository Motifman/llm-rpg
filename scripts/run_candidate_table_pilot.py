#!/usr/bin/env python3
"""Issue #1429 の候補表介入を、固定した 5 失敗 + 5 対応正常例で実行する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from ai_rpg_world.application.llm.services.dynamic_argument_candidates import (  # noqa: E402
    evaluate_dynamic_argument_choice,
)
from ai_rpg_world.application.llm.services.prompt_dataset_capture import (  # noqa: E402
    reconstruct_request,
)

ACTION_INSTRUCTION = "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。"

# 失敗例ごとに、同じモデル・人物・ツールのうち tick が最も近い正常例を固定した。
CASES = (
    ("issue_1429_gemma_baseline_004", "failure", "4e49dc8d-d7e7-4205-b0ec-19ea7898d97d"),
    ("issue_1429_gemma_baseline_004", "valid", "2be76e17-7896-4895-9fc7-8cdc57bf4edc"),
    ("issue_1429_deepseek_baseline_004", "failure", "abae3e77-7c77-4033-928a-3699e8b8f381"),
    ("issue_1429_deepseek_baseline_004", "valid", "90acfb4a-5a00-48a1-9552-0c22f0f0a715"),
    ("issue_1429_deepseek_baseline_004", "failure", "8727d865-6899-4f8d-a337-32f80f6e3896"),
    ("issue_1429_deepseek_baseline_004", "valid", "29692a76-1193-489d-afa0-60a71105d46d"),
    ("issue_1429_deepseek_baseline_004", "failure", "58173022-2b4e-4b7c-9b29-4f9570aa543f"),
    ("issue_1429_deepseek_baseline_004", "valid", "6112c45a-56ae-4309-b864-f4099c1b1441"),
    ("issue_1429_deepseek_baseline_004", "failure", "7ef69241-1cd9-47ee-84d4-87e0d26ddd2b"),
    ("issue_1429_deepseek_baseline_004", "valid", "508565e7-410a-41fe-9037-7c05bdb4b043"),
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def insert_candidate_table(user_prompt: str, table: str) -> str:
    """本番介入位置として、末尾の行動指示の直前へ候補表だけを挿入する。"""
    if user_prompt.count(ACTION_INSTRUCTION) != 1:
        raise ValueError("行動指示が一意に見つからない")
    return user_prompt.replace(ACTION_INSTRUCTION, f"{table}\n\n{ACTION_INSTRUCTION}", 1)


def _extract_output(response: Any) -> dict[str, Any]:
    message = response.choices[0].message
    tool_calls = getattr(message, "tool_calls", None) or []
    if not tool_calls:
        return {"name": None, "arguments": {}, "error": "no_tool_calls"}
    call = tool_calls[0].function
    arguments = json.loads(call.arguments) if isinstance(call.arguments, str) else (call.arguments or {})
    return {"name": call.name, "arguments": arguments, "error": None}


def _load_cases(runs_dir: Path) -> list[dict[str, Any]]:
    loaded = []
    for run_name, cohort, call_id in CASES:
        dataset = runs_dir / run_name / "prompt_dataset"
        calls = {row["llm_call_id"]: row for row in _read_jsonl(dataset / "calls.jsonl")}
        results = {row["llm_call_id"]: row["result"] for row in _read_jsonl(dataset / "turn_results.jsonl")}
        systems = {row["system_prompt_id"]: row for row in _read_jsonl(dataset / "system_prompts.jsonl")}
        toolsets = {row["toolset_id"]: row for row in _read_jsonl(dataset / "toolsets.jsonl")}
        call = calls[call_id]
        kwargs = reconstruct_request(call, systems, toolsets)
        table = call["dynamic_argument_candidates"]["rendered"]
        if not table:
            raise ValueError(f"{call_id}: 候補表が空")
        messages = [dict(message) for message in kwargs["messages"]]
        messages[-1] = dict(messages[-1])
        messages[-1]["content"] = insert_candidate_table(messages[-1]["content"], table)
        kwargs["messages"] = messages
        kwargs["api_base"] = "https://openrouter.ai/api/v1"
        loaded.append(
            {
                "run": run_name,
                "cohort": cohort,
                "call": call,
                "original_result": results.get(call_id),
                "table": table,
                "kwargs": kwargs,
            }
        )
    return loaded


def _cost(response: Any) -> float:
    return float(getattr(response, "_hidden_params", {}).get("response_cost") or 0.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "var" / "runs")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--secret-env-file",
        type=Path,
        default=REPO_ROOT / ".env",
        help="API キーを読む .env。値は成果物へ保存しない。",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cases = _load_cases(args.runs_dir)
    manifest = []
    for case in cases:
        call = case["call"]
        original_output = call.get("output") or {}
        original_eval = evaluate_dynamic_argument_choice(
            original_output.get("name"),
            original_output.get("arguments") or {},
            call["dynamic_argument_candidates"],
        )
        manifest.append(
            {
                "run": case["run"],
                "cohort": case["cohort"],
                "llm_call_id": call["llm_call_id"],
                "world_tick": call["world_tick"],
                "player_id": call["player_id"],
                "character_name": call["character_name"],
                "model": call["model"],
                "original_output": original_output,
                "original_result": case["original_result"],
                "original_candidate_evaluation": original_eval,
                "candidate_snapshot": call["dynamic_argument_candidates"],
                "intervened_prompt_sha256": hashlib.sha256(
                    case["kwargs"]["messages"][-1]["content"].encode()
                ).hexdigest(),
            }
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "cases": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.dry_run:
        print(f"対象 {len(cases)} 件。API 呼び出しなし。manifest: {args.out_dir / 'manifest.json'}")
        return 0

    results_path = args.out_dir / "results.jsonl"
    if results_path.exists():
        raise FileExistsError(f"既存結果へ追記しない: {results_path}")

    try:
        from dotenv import load_dotenv

        load_dotenv(args.secret_env_file)
    except ImportError:
        pass
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY または OPENROUTER_API_KEY がない")

    import litellm

    rows = []
    for index, case in enumerate(cases, 1):
        call = case["call"]
        started = time.perf_counter()
        try:
            response = litellm.completion(**case["kwargs"], api_key=api_key)
            output = _extract_output(response)
            evaluation = evaluate_dynamic_argument_choice(
                output["name"], output["arguments"], call["dynamic_argument_candidates"]
            )
            usage = getattr(response, "usage", None)
            row = {
                "error": output.pop("error"),
                "output": output,
                "candidate_evaluation": evaluation,
                "cost_usd": _cost(response),
                "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            }
        except Exception as exc:  # noqa: BLE001 - 1 件の失敗も成果物へ残す
            row = {
                "error": f"{type(exc).__name__}: {exc}",
                "output": None,
                "candidate_evaluation": None,
                "cost_usd": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }
        row.update(
            {
                "run": case["run"],
                "cohort": case["cohort"],
                "llm_call_id": call["llm_call_id"],
                "world_tick": call["world_tick"],
                "player_id": call["player_id"],
                "character_name": call["character_name"],
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )
        rows.append(row)
        with results_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[{index}/{len(cases)}] {case['cohort']} {call['character_name']} -> {row['candidate_evaluation']}", flush=True)

    summary = {
        "total": len(rows),
        "api_errors": sum(row["error"] is not None for row in rows),
        "failure_cases": sum(row["cohort"] == "failure" for row in rows),
        "failure_cases_valid_after_intervention": sum(
            row["cohort"] == "failure"
            and (row["candidate_evaluation"] or {}).get("status") == "valid"
            for row in rows
        ),
        "valid_cases": sum(row["cohort"] == "valid" for row in rows),
        "valid_cases_still_valid": sum(
            row["cohort"] == "valid"
            and (row["candidate_evaluation"] or {}).get("status") == "valid"
            for row in rows
        ),
        "status_counts": {
            status: sum((row["candidate_evaluation"] or {}).get("status") == status for row in rows)
            for status in ("valid", "invalid", "not_applicable")
        },
        "cost_usd": sum(row["cost_usd"] for row in rows),
        "prompt_tokens": sum(row["prompt_tokens"] for row in rows),
        "completion_tokens": sum(row["completion_tokens"] for row in rows),
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
