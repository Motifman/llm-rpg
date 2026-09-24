"""Issue #1429: Jev と行動直前の動的引数表を、同じ失敗事例で比較する。

このスクリプトの入力は、過去 run の prompt dataset と既存 Jev デモが抽出した
失敗事例である。候補表方式は保存済み request を再生し、ユーザープロンプトの
行動指示直前へだけ候補表を加える。元の出力の文字列変換は行わない。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_REPO_ROOT = Path(__file__).resolve().parents[1]
_NO_MATCH = "__no_match__"


@dataclass(frozen=True)
class CaseLabel:
    """比較事例の独立した正解。None は候補内に正解がないことを表す。"""

    case_id: str
    expected: str | None


@dataclass(frozen=True)
class EvaluatedChoice:
    """一方式による選択を、正解ラベルに対して評価できる形で持つ。"""

    label: CaseLabel
    chosen: str | None
    disposition: Literal["selected", "no_match", "unresolved", "error"]
    latency_ms: float
    cost_usd: float


def _quoted(values: list[str]) -> str:
    return ", ".join(f'"{value}"' for value in values)


def build_candidate_table(
    *,
    kind: Literal["action_name", "target_name"],
    tool: str,
    argument_name: str,
    target: str,
    candidates: list[str],
) -> str:
    """保存済み runtime 候補を、ツールと引数の対応を保った表へ整形する。"""
    lines = ["【現在指定できる引数】"]
    if kind == "action_name":
        lines.append(f'- {tool}.target_label: "{target}"')
        lines.append(f'- {tool}.{argument_name} ("{target}"): {_quoted(candidates)}')
    else:
        lines.append(f"- {tool}.{argument_name}: {_quoted(candidates)}")
    lines.append("※ 一覧にあることは操作の成功を保証しない。現在の状態や前提条件によって失敗する場合がある。")
    return "\n".join(lines)


def summarize_choices(rows: list[EvaluatedChoice]) -> dict[str, float | int]:
    """候補選択を多値分類と救済の二値分類の両方で集計する。"""
    total = len(rows)
    correct = sum(row.chosen == row.label.expected for row in rows)
    selected = [row for row in rows if row.chosen is not None]
    true_positive = sum(row.label.expected is not None and row.chosen == row.label.expected for row in rows)
    expected_positive = sum(row.label.expected is not None for row in rows)
    return {
        "total": total,
        "accuracy": correct / total if total else 0.0,
        "precision": true_positive / len(selected) if selected else 0.0,
        "recall": true_positive / expected_positive if expected_positive else 0.0,
        "wrong_selection": sum(row.chosen is not None and row.chosen != row.label.expected for row in rows),
        "correct_no_match": sum(row.label.expected is None and row.disposition == "no_match" for row in rows),
        "unresolved": sum(row.disposition == "unresolved" for row in rows),
        "errors": sum(row.disposition == "error" for row in rows),
        "latency_ms_total": sum(row.latency_ms for row in rows),
        "cost_usd_total": sum(row.cost_usd for row in rows),
    }


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _argument_name(tool: str, arguments: dict, written: str) -> str:
    for name in ("target_label", "item_label", "destination_label", "object_label"):
        if arguments.get(name) == written:
            return name
    return "target_label"


def _label_action(written: str, candidates: list[str]) -> tuple[str | None, str]:
    """結果を見る前に固定した、人手判断を再現可能な規則へ書き下す。"""
    normalized = written.strip().strip('"').strip("'")
    for candidate in candidates:
        if candidate in normalized or normalized in candidate:
            return candidate, "候補名または表示行を含む"
    aliases = {
        "search": "search_debris",
        "open": "take_lantern",
        "operate_main_panel": "restore_power",
        "復旧を試みる": "restore_power",
        "restore_lighting": "restore_power",
        "復旧する": "restore_power",
        "照明を復旧する": "restore_power",
        "read_schedule": "read_board",
        "海を見渡す": "scout_sea",
        "貝を採る": "gather_shellfish",
        "写真を見つめる": "examine_photo",
        "観測記録を照合する": "reconcile_observation_records",
    }
    alias = aliases.get(normalized)
    if alias in candidates:
        return alias, "独立に定めた同義表現"
    if normalized == "examine":
        for candidate in ("search_debris", "search_cockpit", "search"):
            if candidate in candidates:
                return candidate, "調べる意図と探索操作が一致"
    return None, "候補のどの操作とも意図が一致しない"


def _label_target(written: str, candidates: list[str]) -> tuple[str | None, str]:
    normalized = written.strip().strip('"').strip("'")
    aliases = {
        "East Shrine": "東の祭壇",
        "东の祭壇": "東の祭壇",
        "漂着物": "波が運んだ漂着物",
        "貝": "貝の岩棚",
    }
    expected = aliases.get(normalized)
    if expected in candidates:
        return expected, "独立に定めた翻訳または短縮表現"
    return None, "候補内に同じ対象を指す名前がない"


def extract_dataset(config: dict) -> dict:
    """既存デモの事例を、保存済み主モデル request と結合する。"""
    runs_dir = Path(config["source_runs_dir"])
    sources = (
        ("action_name", Path(config["action_cases"]), "INTERACTION_ACTION_NOT_FOUND"),
        ("target_name", Path(config["target_cases"]), "INVALID_TARGET_LABEL"),
    )
    rows: list[dict] = []
    omitted: dict[str, int] = {}
    for kind, cases_path, error_code in sources:
        cases = [item for item in json.loads(cases_path.read_text())["cases"] if not item.get("is_control")]
        for case in cases:
            dataset = runs_dir / case["run"] / "prompt_dataset"
            if not dataset.exists():
                omitted[kind] = omitted.get(kind, 0) + 1
                continue
            calls = {item["llm_call_id"]: item for item in _read_jsonl(dataset / "calls.jsonl")}
            result = next(
                (
                    item
                    for item in _read_jsonl(dataset / "turn_results.jsonl")
                    if item.get("world_tick") == case["tick"]
                    and item.get("player_id") == case["player_id"]
                    and (item.get("result") or {}).get("action_result_error_code") == error_code
                ),
                None,
            )
            if result is None or result["llm_call_id"] not in calls:
                omitted[kind] = omitted.get(kind, 0) + 1
                continue
            call = calls[result["llm_call_id"]]
            system_prompts = {
                item["system_prompt_id"]: item["content"] for item in _read_jsonl(dataset / "system_prompts.jsonl")
            }
            toolsets = {item["toolset_id"]: item["tools"] for item in _read_jsonl(dataset / "toolsets.jsonl")}
            request = call["request"]["kwargs"]
            messages = []
            for message in request["messages"]:
                messages.append(
                    {
                        "role": message["role"],
                        "content": message.get("content") or system_prompts[message["content_ref"]],
                    }
                )
            output = call["output"]
            tool = output["name"]
            arguments = output.get("arguments") or {}
            candidates = case.get("available") or list(case.get("candidates") or {})
            target = case.get("target") or ""
            argument_name = "action_name" if kind == "action_name" else _argument_name(tool, arguments, case["written"])
            expected, rationale = (
                _label_action(case["written"], candidates)
                if kind == "action_name"
                else _label_target(case["written"], candidates)
            )
            case_id = f"{kind}:{case['run']}:{case['tick']}:{case['player_id']}"
            rows.append(
                {
                    "case_id": case_id,
                    "kind": kind,
                    "run": case["run"],
                    "tick": case["tick"],
                    "player_id": case["player_id"],
                    "written": case["written"],
                    "target": target,
                    "inner_thought": case.get("inner_thought") or "",
                    "tool": tool,
                    "argument_name": argument_name,
                    "candidates": candidates,
                    "expected": expected,
                    "label_rationale": rationale,
                    "messages": messages,
                    "tools": toolsets[call["prompt"]["toolset_id"]],
                    "original_model": call["model"]["model"],
                    "original_prompt_tokens": call["metrics"]["prompt_tokens"],
                }
            )
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()
    return {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(encoded).hexdigest(),
        "omitted_without_complete_prompt": omitted,
        "cases": rows,
    }


def _insert_table(user_prompt: str, table: str) -> str:
    instruction = "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。"
    if instruction not in user_prompt:
        return f"{user_prompt.rstrip()}\n\n{table}"
    return user_prompt.replace(instruction, f"{table}\n\n{instruction}", 1)


def _choice_from_output(case: dict, name: str | None, arguments: dict) -> tuple[str | None, str]:
    if name != case["tool"]:
        return None, "no_match"
    chosen = arguments.get(case["argument_name"])
    if chosen in case["candidates"]:
        return str(chosen), "selected"
    return None, "unresolved"


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    return sorted(values)[min(len(values) - 1, int(len(values) * fraction))]


def run_experiment(config: dict, dataset: dict) -> dict:
    from dotenv import load_dotenv
    from litellm import completion, token_counter
    from scripts.jev_action_name_rescue_demo import Case as ActionCase
    from scripts.jev_action_name_rescue_demo import judge_jev as judge_action
    from scripts.jev_target_label_rescue_demo import Case as TargetCase
    from scripts.jev_target_label_rescue_demo import judge_jev as judge_target

    from ai_rpg_world.infrastructure.llm.jev_typed_judgment_adapter import JevTypedJudgmentAdapter

    load_dotenv(config["secret_env_file"])
    api_key = (os.environ.get(config["api_key_env"]) or "").strip()
    if not api_key:
        raise RuntimeError(f"秘密情報 {config['api_key_env']} がありません")
    jev = JevTypedJudgmentAdapter(
        api_key=api_key,
        endpoint=config["jev"]["endpoint"],
        model=config["jev"]["model"],
        timeout_seconds=config["jev"]["timeout_seconds"],
        rate_limit_retry_attempts=config["jev"]["retry_attempts"],
    )
    results = []
    for index, case in enumerate(dataset["cases"], 1):
        table = build_candidate_table(
            kind=case["kind"],
            tool=case["tool"],
            argument_name=case["argument_name"],
            target=case["target"],
            candidates=case["candidates"],
        )
        messages = [dict(message) for message in case["messages"]]
        messages[-1]["content"] = _insert_table(messages[-1]["content"], table)
        token_increase = token_counter(model=config["candidate_table"]["model"], messages=messages) - token_counter(
            model=config["candidate_table"]["model"], messages=case["messages"]
        )
        started = time.perf_counter()
        try:
            response = completion(
                model=config["candidate_table"]["model"],
                messages=messages,
                tools=case["tools"],
                tool_choice="required",
                api_key=api_key,
                timeout=config["candidate_table"]["timeout_seconds"],
                temperature=config["candidate_table"]["temperature"],
            )
            latency_ms = (time.perf_counter() - started) * 1000
            call = response.choices[0].message.tool_calls[0].function
            arguments = json.loads(call.arguments)
            chosen, disposition = _choice_from_output(case, call.name, arguments)
            usage = response.usage
            cost = float(getattr(response, "_hidden_params", {}).get("response_cost") or 0.0)
            candidate = {
                "chosen": chosen,
                "disposition": disposition,
                "tool": call.name,
                "arguments": arguments,
                "latency_ms": round(latency_ms, 1),
                "cost_usd": cost,
                "prompt_tokens": int(usage.prompt_tokens),
                "input_token_increase_estimate": token_increase,
                "error": None,
            }
        except Exception as exc:  # 実験成果物へ失敗を残し、他事例を続行する
            candidate = {
                "chosen": None,
                "disposition": "error",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "cost_usd": 0.0,
                "input_token_increase_estimate": token_increase,
                "error": f"{type(exc).__name__}: {exc}",
            }
        if case["kind"] == "action_name":
            jev_case = ActionCase(
                run=case["run"],
                tick=case["tick"],
                player_id=case["player_id"],
                written=case["written"],
                target=case["target"],
                inner_thought=case["inner_thought"],
                available=case["candidates"],
            )
            outcome = judge_action(jev_case, jev, config["jev"]["min_confidence"], labels=None, variant="full")
        else:
            jev_case = TargetCase(
                run=case["run"],
                tick=case["tick"],
                player_id=case["player_id"],
                tool=case["tool"],
                written=case["written"],
                inner_thought=case["inner_thought"],
                candidates={name: "" for name in case["candidates"]},
            )
            outcome = judge_target(jev_case, jev, config["jev"]["min_confidence"])
        jev_disposition = (
            "selected"
            if outcome.chosen
            else ("no_match" if outcome.raw_choice == _NO_MATCH else ("error" if outcome.error else "unresolved"))
        )
        results.append(
            {
                "case": {k: v for k, v in case.items() if k not in ("messages", "tools")},
                "candidate_table": candidate,
                "jev": {
                    "chosen": outcome.chosen,
                    "raw_choice": outcome.raw_choice,
                    "disposition": jev_disposition,
                    "score": outcome.score,
                    "confidence": outcome.confidence,
                    "latency_ms": outcome.latency_ms,
                    "cost_usd": None,
                    "error": outcome.error,
                },
            }
        )
        print(f"{index}/{len(dataset['cases'])} {case['case_id']}")
    return {"config": config, "dataset_sha256": dataset["source_sha256"], "results": results}


def build_report(payload: dict) -> dict:
    report = {"conditions": payload["config"], "dataset_sha256": payload["dataset_sha256"], "by_kind": {}}
    for kind in ("action_name", "target_name"):
        subset = [row for row in payload["results"] if row["case"]["kind"] == kind]
        methods = {}
        for method in ("jev", "candidate_table"):
            evaluated = [
                EvaluatedChoice(
                    CaseLabel(row["case"]["case_id"], row["case"]["expected"]),
                    row[method]["chosen"],
                    row[method]["disposition"],
                    row[method].get("latency_ms") or 0.0,
                    row[method].get("cost_usd") or 0.0,
                )
                for row in subset
            ]
            summary = summarize_choices(evaluated)
            latencies = [row[method].get("latency_ms") for row in subset if row[method].get("latency_ms") is not None]
            summary.update(
                {
                    "latency_ms_p50": statistics.median(latencies) if latencies else None,
                    "latency_ms_p90": _percentile(latencies, 0.9),
                }
            )
            if method == "jev":
                summary["cost_usd_total"] = None
            else:
                summary["input_token_increase_total"] = sum(
                    row[method].get("input_token_increase_estimate", 0) for row in subset
                )
            methods[method] = summary
        report["by_kind"][kind] = methods
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("extract", "run", "report"))
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    dataset_path = Path(config["dataset_path"])
    results_path = Path(config["results_path"])
    if args.command == "extract":
        payload = extract_dataset(config)
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        dataset_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(dataset_path)
    elif args.command == "run":
        payload = run_experiment(config, json.loads(dataset_path.read_text()))
        results_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(results_path)
    else:
        report = build_report(json.loads(results_path.read_text()))
        out = Path(config["report_path"])
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
