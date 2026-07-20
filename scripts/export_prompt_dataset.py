"""prompt_dataset 生 JSONL を Hugging Face datasets 用ディレクトリへ export する。"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import pyarrow.parquet as pq
from datasets import Dataset


_TABLE_DIRS = {
    "default": "data",
    "system_prompts": "system_prompts",
    "toolsets": "toolsets",
    "runs": "runs",
}


@dataclass(frozen=True)
class ExportSummary:
    """export 結果の行数と出力先。"""

    out_dir: Path
    turns_count: int
    system_prompts_count: int
    toolsets_count: int
    runs_count: int
    splits: tuple[str, ...]


def export_prompt_dataset(
    *,
    run_dirs: Iterable[Path],
    out_dir: Path,
    split_map_path: Optional[Path] = None,
    include_raw: bool = True,
) -> ExportSummary:
    """複数 run の prompt_dataset を統合して Parquet dataset を生成する。"""

    run_dirs = [Path(run_dir) for run_dir in run_dirs]
    if not run_dirs:
        raise ValueError("at least one --run-dir is required")

    split_map = _load_split_map(split_map_path)
    loaded_runs = [_load_run(run_dir) for run_dir in run_dirs]
    _validate_unique_run_ids(loaded_runs)

    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    turns_by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    runs_by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    system_rows_by_id: dict[str, dict[str, Any]] = {}
    toolset_rows_by_id: dict[str, dict[str, Any]] = {}
    system_ids_by_split: dict[str, set[str]] = defaultdict(set)
    toolset_ids_by_split: dict[str, set[str]] = defaultdict(set)

    for loaded in loaded_runs:
        split = _resolve_split(loaded["run_id"], split_map)
        calls = loaded["calls"]
        turn_results_by_id = _index_by_key(
            loaded["turn_results"], "llm_call_id", table_name="turn_results"
        )
        for call in calls:
            llm_call_id = _required_str(call, "llm_call_id", table_name="calls")
            result_row = turn_results_by_id.get(llm_call_id)
            if result_row is None:
                raise ValueError(
                    f"turn_results.jsonl missing llm_call_id={llm_call_id!r}"
                )
            turn = dict(call)
            turn["result"] = result_row.get("result", {})
            turn["turn_result"] = result_row
            turn["result_missing"] = False
            turns_by_split[split].append(turn)
            system_id = _extract_system_prompt_id(call)
            if system_id:
                system_ids_by_split[split].add(system_id)
            toolset_id = _extract_toolset_id(call)
            if toolset_id:
                toolset_ids_by_split[split].add(toolset_id)

        run_row = dict(loaded["run"])
        run_row["source_run_dir"] = str(loaded["run_dir"])
        runs_by_split[split].append(run_row)

        _merge_unique_rows(
            system_rows_by_id,
            loaded["system_prompts"],
            key="system_prompt_id",
            table_name="system_prompts",
        )
        _merge_unique_rows(
            toolset_rows_by_id,
            loaded["toolsets"],
            key="toolset_id",
            table_name="toolsets",
        )

    split_names = tuple(sorted(turns_by_split))
    for split in split_names:
        _write_parquet(
            out_dir / _TABLE_DIRS["default"] / f"{split}-00000-of-00001.parquet",
            turns_by_split[split],
        )
        _write_parquet(
            out_dir / _TABLE_DIRS["system_prompts"] / f"{split}-00000-of-00001.parquet",
            [system_rows_by_id[row_id] for row_id in sorted(system_ids_by_split[split])],
        )
        _write_parquet(
            out_dir / _TABLE_DIRS["toolsets"] / f"{split}-00000-of-00001.parquet",
            [toolset_rows_by_id[row_id] for row_id in sorted(toolset_ids_by_split[split])],
        )
        _write_parquet(
            out_dir / _TABLE_DIRS["runs"] / f"{split}-00000-of-00001.parquet",
            runs_by_split[split],
        )

    if include_raw:
        _write_raw_archive(out_dir / "raw", loaded_runs)
    _write_readme(out_dir, split_names)
    _write_dataset_infos(out_dir, split_names, turns_by_split, runs_by_split)

    return ExportSummary(
        out_dir=out_dir,
        turns_count=sum(len(rows) for rows in turns_by_split.values()),
        system_prompts_count=len(system_rows_by_id),
        toolsets_count=len(toolset_rows_by_id),
        runs_count=len(loaded_runs),
        splits=split_names,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        action="append",
        required=True,
        type=Path,
        help="prompt_dataset/ を含む run directory。複数指定可。",
    )
    parser.add_argument("--out", required=True, type=Path, help="export 先 directory")
    parser.add_argument("--split-map", type=Path, help="run_id を split に割り当てる JSON")
    parser.add_argument(
        "--include-raw",
        choices=("true", "false"),
        default="true",
        help="raw JSONL gzip を同梱するか。",
    )
    args = parser.parse_args(argv)

    summary = export_prompt_dataset(
        run_dirs=args.run_dir,
        out_dir=args.out,
        split_map_path=args.split_map,
        include_raw=args.include_raw == "true",
    )
    print(
        json.dumps(
            {
                "out_dir": str(summary.out_dir),
                "turns_count": summary.turns_count,
                "system_prompts_count": summary.system_prompts_count,
                "toolsets_count": summary.toolsets_count,
                "runs_count": summary.runs_count,
                "splits": list(summary.splits),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _load_run(run_dir: Path) -> dict[str, Any]:
    dataset_dir = run_dir / "prompt_dataset"
    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"prompt_dataset directory not found: {dataset_dir}")
    run = _read_json(dataset_dir / "run.json")
    run_id = _required_str(run, "run_id", table_name="run")
    return {
        "run_dir": run_dir,
        "dataset_dir": dataset_dir,
        "run": run,
        "run_id": run_id,
        "calls": _read_jsonl(dataset_dir / "calls.jsonl"),
        "turn_results": _read_jsonl(dataset_dir / "turn_results.jsonl"),
        "system_prompts": _read_jsonl(dataset_dir / "system_prompts.jsonl"),
        "toolsets": _read_jsonl(dataset_dir / "toolsets.jsonl"),
    }


def _load_split_map(path: Optional[Path]) -> dict[str, str]:
    if path is None:
        return {}
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("--split-map must be a JSON object")
    result: dict[str, str] = {}
    for split, run_ids in raw.items():
        if not isinstance(split, str) or not split:
            raise ValueError("--split-map split names must be non-empty strings")
        if not isinstance(run_ids, list):
            raise ValueError("--split-map values must be arrays of run_id")
        for run_id in run_ids:
            if not isinstance(run_id, str) or not run_id:
                raise ValueError("--split-map run_id values must be non-empty strings")
            if run_id in result:
                raise ValueError(f"run_id {run_id!r} appears in multiple splits")
            result[run_id] = split
    return result


def _resolve_split(run_id: str, split_map: Mapping[str, str]) -> str:
    if not split_map:
        return "train"
    try:
        return split_map[run_id]
    except KeyError as exc:
        raise ValueError(f"run_id {run_id!r} is missing from --split-map") from exc


def _validate_unique_run_ids(loaded_runs: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for loaded in loaded_runs:
        run_id = loaded["run_id"]
        if run_id in seen:
            raise ValueError(f"duplicate run_id: {run_id}")
        seen.add(run_id)


def _index_by_key(
    rows: list[dict[str, Any]],
    key: str,
    *,
    table_name: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = _required_str(row, key, table_name=table_name)
        if value in result:
            raise ValueError(f"duplicate {table_name}.{key}: {value}")
        result[value] = row
    return result


def _merge_unique_rows(
    destination: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    key: str,
    table_name: str,
) -> None:
    for row in rows:
        value = _required_str(row, key, table_name=table_name)
        existing = destination.get(value)
        if existing is not None:
            continue
        destination[value] = row


def _extract_system_prompt_id(call: Mapping[str, Any]) -> Optional[str]:
    prompt = call.get("prompt")
    if isinstance(prompt, dict) and isinstance(prompt.get("system_prompt_id"), str):
        return prompt["system_prompt_id"]
    kwargs = _request_kwargs(call)
    for message in kwargs.get("messages", []):
        if isinstance(message, dict) and isinstance(message.get("content_ref"), str):
            return message["content_ref"]
    return None


def _extract_toolset_id(call: Mapping[str, Any]) -> Optional[str]:
    prompt = call.get("prompt")
    if isinstance(prompt, dict) and isinstance(prompt.get("toolset_id"), str):
        return prompt["toolset_id"]
    kwargs = _request_kwargs(call)
    tools_ref = kwargs.get("tools_ref")
    return tools_ref if isinstance(tools_ref, str) else None


def _request_kwargs(call: Mapping[str, Any]) -> dict[str, Any]:
    request = call.get("request")
    if not isinstance(request, dict):
        return {}
    kwargs = request.get("kwargs")
    return kwargs if isinstance(kwargs, dict) else {}


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset = Dataset.from_list([_json_stringify_nested(row) for row in rows])
    pq.write_table(dataset.data.table, path, compression="zstd")


def _json_stringify_nested(row: Mapping[str, Any]) -> dict[str, Any]:
    """Parquet で壊れやすい任意 JSON を文字列として保存する。

    provider response や tool schema は空 object や揺れる field を含む。dummy field を
    足すと replay 忠実性が落ちるため、可変 JSON は JSON 文字列で保持する。
    """

    converted: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            converted[key] = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        else:
            converted[key] = value
    return converted


def _write_raw_archive(raw_dir: Path, loaded_runs: list[dict[str, Any]]) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for loaded in loaded_runs:
        run_raw_dir = raw_dir / loaded["run_id"]
        run_raw_dir.mkdir(parents=True, exist_ok=True)
        dataset_dir = loaded["dataset_dir"]
        shutil.copyfile(dataset_dir / "run.json", run_raw_dir / "run.json")
        for name in (
            "calls.jsonl",
            "turn_results.jsonl",
            "system_prompts.jsonl",
            "toolsets.jsonl",
        ):
            with (dataset_dir / name).open("rb") as src:
                with gzip.open(run_raw_dir / f"{name}.gz", "wb") as dst:
                    shutil.copyfileobj(src, dst)


def _write_readme(out_dir: Path, splits: tuple[str, ...]) -> None:
    configs = []
    for config_name, directory in _TABLE_DIRS.items():
        config = {
            "config_name": config_name,
            "data_files": [
                {
                    "split": split,
                    "path": f"{directory}/{split}-00000-of-00001.parquet",
                }
                for split in splits
            ],
        }
        configs.append(config)
    metadata = json.dumps({"configs": configs}, ensure_ascii=False, indent=2)
    text = f"""---
{metadata}
---
# llm-rpg prompt dataset

## Dataset Summary

llm-rpg の実験 run から作った LLM tool-use prompt dataset。
既定 config は `turns` 相当で、1 行が 1 LLM 呼び出しを表す。

## Dataset Structure

- `load_dataset(path)` または default config: `turns`
- `load_dataset(path, "system_prompts")`: system prompt 本文
- `load_dataset(path, "toolsets")`: LLM に渡した tools 配列
- `load_dataset(path, "runs")`: run 単位の provenance

join key は `run_id`、`llm_call_id`、`system_prompt_id`、`toolset_id`。
`turns.request.kwargs` の `content_ref` / `tools_ref` を sidecar と結合すると
`reconstruct_request` で replay 用 request を復元できる。

## Limitations

sampling parameter は保存するが、モデル側の確率的な揺らぎは除去しない。
ゲーム内合成データであり、現実世界の一般対話ではない。
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def _write_dataset_infos(
    out_dir: Path,
    splits: tuple[str, ...],
    turns_by_split: Mapping[str, list[dict[str, Any]]],
    runs_by_split: Mapping[str, list[dict[str, Any]]],
) -> None:
    infos: dict[str, dict[str, Any]] = {}
    for config_name in _TABLE_DIRS:
        if config_name == "default":
            description = "1 row = 1 LLM call joined with its turn result"
        elif config_name == "runs":
            description = "run provenance sidecar"
        else:
            description = f"{config_name} sidecar"
        infos[config_name] = {
            "description": description,
            "citation": "",
            "homepage": "",
            "license": "",
            "download_size": None,
            "dataset_size": None,
        }
    (out_dir / "dataset_infos.json").write_text(
        json.dumps(infos, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


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


def _required_str(row: Mapping[str, Any], key: str, *, table_name: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{table_name}.{key} must be a non-empty string")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
