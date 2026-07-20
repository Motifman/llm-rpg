"""prompt_dataset の raw capture と trace の整合性を検査する。"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


@dataclass(frozen=True)
class CheckResult:
    """prompt dataset 検査結果。"""

    ok: bool
    errors: list[str]
    summary: dict[str, int]


def check_prompt_dataset(
    *,
    run_dirs: Iterable[Path],
    split_map_path: Optional[Path] = None,
) -> CheckResult:
    """複数 run の prompt_dataset が export 前提を満たすか検査する。"""

    errors: list[str] = []
    run_dirs = [Path(run_dir) for run_dir in run_dirs]
    if not run_dirs:
        errors.append("at least one --run-dir is required")
        return _result(errors, runs_count=0, calls_count=0, trace_llm_calls_count=0)

    loaded_runs: list[dict[str, Any]] = []
    total_calls = 0
    total_trace_calls = 0
    for run_dir in run_dirs:
        loaded = _load_run(run_dir, errors)
        if loaded is None:
            continue
        loaded_runs.append(loaded)
        total_calls += len(loaded["calls"])
        total_trace_calls += len(loaded["trace_llm_calls"])
        _check_run(loaded, errors)

    _check_unique_run_ids(loaded_runs, errors)
    if split_map_path is not None:
        _check_split_map(split_map_path, loaded_runs, errors)

    return _result(
        errors,
        runs_count=len(loaded_runs),
        calls_count=total_calls,
        trace_llm_calls_count=total_trace_calls,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        action="append",
        required=True,
        type=Path,
        help="prompt_dataset/ と trace.jsonl を含む run directory。複数指定可。",
    )
    parser.add_argument("--split-map", type=Path, help="run_id を split に割り当てる JSON")
    args = parser.parse_args(argv)

    result = check_prompt_dataset(run_dirs=args.run_dir, split_map_path=args.split_map)
    print(
        json.dumps(
            {
                "ok": result.ok,
                "errors": result.errors,
                "summary": result.summary,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result.ok else 1


def _load_run(run_dir: Path, errors: list[str]) -> Optional[dict[str, Any]]:
    dataset_dir = run_dir / "prompt_dataset"
    try:
        run = _read_json(dataset_dir / "run.json")
        capture_status = _read_json(dataset_dir / "capture_status.json")
        calls = _read_jsonl(dataset_dir / "calls.jsonl")
        turn_results = _read_jsonl(dataset_dir / "turn_results.jsonl")
        system_prompts = _read_jsonl(dataset_dir / "system_prompts.jsonl")
        toolsets = _read_jsonl(dataset_dir / "toolsets.jsonl")
        trace_events = _read_jsonl(run_dir / "trace.jsonl")
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{run_dir}: {exc}")
        return None
    run_id = _str_value(run, "run_id")
    if run_id is None:
        errors.append(f"{dataset_dir / 'run.json'}: run_id must be non-empty string")
        return None
    return {
        "run_dir": run_dir,
        "dataset_dir": dataset_dir,
        "run_id": run_id,
        "run": run,
        "capture_status": capture_status,
        "calls": calls,
        "turn_results": turn_results,
        "system_prompts": system_prompts,
        "toolsets": toolsets,
        "trace_llm_calls": [
            event for event in trace_events if event.get("kind") == "llm_call"
        ],
    }


def _check_run(loaded: Mapping[str, Any], errors: list[str]) -> None:
    run_id = loaded["run_id"]
    calls = loaded["calls"]
    turn_results = loaded["turn_results"]
    trace_llm_calls = loaded["trace_llm_calls"]
    prefix = str(loaded["run_dir"])

    status = loaded["capture_status"]
    if status.get("run_id") != run_id:
        errors.append(f"{prefix}: capture_status.run_id does not match run_id {run_id!r}")
    if status.get("capture_incomplete") is not False:
        errors.append(f"{prefix}: capture_incomplete must be false")

    call_ids = _index_rows(calls, "llm_call_id", "calls", prefix, errors)
    result_ids = _index_rows(
        turn_results, "llm_call_id", "turn_results", prefix, errors
    )
    for llm_call_id in sorted(set(call_ids) - set(result_ids)):
        errors.append(f"{prefix}: missing turn_result for llm_call_id {llm_call_id!r}")
    for llm_call_id in sorted(set(result_ids) - set(call_ids)):
        errors.append(f"{prefix}: orphan turn_result for llm_call_id {llm_call_id!r}")

    if len(calls) != len(trace_llm_calls):
        errors.append(
            f"{prefix}: trace llm_call count mismatch "
            f"calls={len(calls)} trace={len(trace_llm_calls)}"
        )
    trace_ids = _trace_llm_call_ids(trace_llm_calls)
    if trace_ids:
        for llm_call_id in sorted(set(call_ids) - trace_ids):
            errors.append(f"{prefix}: missing trace llm_call_id {llm_call_id!r}")
        for llm_call_id in sorted(trace_ids - set(call_ids)):
            errors.append(f"{prefix}: trace has unknown llm_call_id {llm_call_id!r}")

    system_prompt_ids = set(
        _index_rows(
            loaded["system_prompts"],
            "system_prompt_id",
            "system_prompts",
            prefix,
            errors,
        )
    )
    toolset_ids = set(
        _index_rows(loaded["toolsets"], "toolset_id", "toolsets", prefix, errors)
    )
    for call in calls:
        llm_call_id = _str_value(call, "llm_call_id") or "<unknown>"
        system_id = _system_prompt_id(call)
        if system_id is not None and system_id not in system_prompt_ids:
            errors.append(
                f"{prefix}: missing system_prompt {system_id!r} "
                f"referenced by call {llm_call_id!r}"
            )
        toolset_id = _toolset_id(call)
        if toolset_id is not None and toolset_id not in toolset_ids:
            errors.append(
                f"{prefix}: missing toolset {toolset_id!r} "
                f"referenced by call {llm_call_id!r}"
            )


def _check_unique_run_ids(
    loaded_runs: list[Mapping[str, Any]], errors: list[str]
) -> None:
    seen: set[str] = set()
    for loaded in loaded_runs:
        run_id = loaded["run_id"]
        if run_id in seen:
            errors.append(f"duplicate run_id: {run_id!r}")
        seen.add(run_id)


def _check_split_map(
    split_map_path: Path,
    loaded_runs: list[Mapping[str, Any]],
    errors: list[str],
) -> None:
    try:
        raw = _read_json(split_map_path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{split_map_path}: {exc}")
        return
    if not isinstance(raw, dict):
        errors.append(f"{split_map_path}: split-map must be a JSON object")
        return

    assigned: dict[str, str] = {}
    for split, run_ids in raw.items():
        if not isinstance(split, str) or not split:
            errors.append(f"{split_map_path}: split names must be non-empty strings")
            continue
        if not isinstance(run_ids, list):
            errors.append(f"{split_map_path}: split {split!r} value must be array")
            continue
        for run_id in run_ids:
            if not isinstance(run_id, str) or not run_id:
                errors.append(f"{split_map_path}: run_id values must be non-empty strings")
                continue
            previous = assigned.get(run_id)
            if previous is not None:
                errors.append(f"run_id {run_id!r} appears in multiple splits")
            assigned[run_id] = split

    known_run_ids = {loaded["run_id"] for loaded in loaded_runs}
    for run_id in sorted(set(assigned) - known_run_ids):
        errors.append(f"split-map contains unknown run_id {run_id!r}")
    for run_id in sorted(known_run_ids - set(assigned)):
        errors.append(f"run_id {run_id!r} is missing from split-map")


def _index_rows(
    rows: list[Mapping[str, Any]],
    key: str,
    table_name: str,
    prefix: str,
    errors: list[str],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows, start=1):
        value = _str_value(row, key)
        if value is None:
            errors.append(f"{prefix}: {table_name}[{index}].{key} must be non-empty string")
            continue
        if value in result:
            errors.append(f"{prefix}: duplicate {table_name}.{key}: {value!r}")
            continue
        result[value] = row
    return result


def _trace_llm_call_ids(trace_llm_calls: list[Mapping[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for event in trace_llm_calls:
        payload = event.get("payload")
        if isinstance(payload, dict):
            value = payload.get("llm_call_id")
            if isinstance(value, str) and value:
                ids.add(value)
    return ids


def _system_prompt_id(call: Mapping[str, Any]) -> Optional[str]:
    prompt = call.get("prompt")
    if isinstance(prompt, dict):
        value = prompt.get("system_prompt_id")
        if isinstance(value, str) and value:
            return value
    request = call.get("request")
    if isinstance(request, dict):
        rehydration = request.get("rehydration")
        if isinstance(rehydration, dict):
            value = rehydration.get("system_prompt_id")
            if isinstance(value, str) and value:
                return value
    return None


def _toolset_id(call: Mapping[str, Any]) -> Optional[str]:
    prompt = call.get("prompt")
    if isinstance(prompt, dict):
        value = prompt.get("toolset_id")
        if isinstance(value, str) and value:
            return value
    request = call.get("request")
    if isinstance(request, dict):
        rehydration = request.get("rehydration")
        if isinstance(rehydration, dict):
            value = rehydration.get("toolset_id")
            if isinstance(value, str) and value:
                return value
        kwargs = request.get("kwargs")
        if isinstance(kwargs, dict):
            value = kwargs.get("tools_ref")
            if isinstance(value, str) and value:
                return value
    return None


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"required file not found: {path}") from exc


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"required file not found: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no}: JSONL row must be object")
        rows.append(value)
    return rows


def _str_value(row: Mapping[str, Any], key: str) -> Optional[str]:
    value = row.get(key)
    return value if isinstance(value, str) and value else None


def _result(errors: list[str], **summary: int) -> CheckResult:
    return CheckResult(ok=not errors, errors=errors, summary=dict(summary))


if __name__ == "__main__":
    raise SystemExit(main())
