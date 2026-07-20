"""scripts/export_prompt_dataset.py の Hugging Face export 挙動を保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("datasets")
pytest.importorskip("pyarrow")

from datasets import load_dataset

from ai_rpg_world.application.llm.services.prompt_dataset_capture import (
    PromptDatasetCallContext,
    PromptDatasetCaptureSink,
    compute_request_hash,
    reconstruct_request,
)
from scripts.export_prompt_dataset import export_prompt_dataset


class TestExportPromptDataset:
    """prompt_dataset 生 JSONL を Parquet dataset に変換する仕様。"""

    def test_single_run_export_load_dataset_and_reconstruct_request(
        self, tmp_path: Path
    ) -> None:
        """単一 run を export すると、既定 config と sidecar から request を復元できる。"""

        run_dir = _create_prompt_dataset_run(
            tmp_path,
            run_id="run-a",
            llm_call_id="call-a1",
            system_content="あなたはエイダです。",
            tool_name="spot_graph_explore",
        )
        out_dir = tmp_path / "dataset_single"

        summary = export_prompt_dataset(run_dirs=[run_dir], out_dir=out_dir)

        assert summary.turns_count == 1
        assert summary.system_prompts_count == 1
        assert summary.toolsets_count == 1
        assert summary.runs_count == 1
        assert (out_dir / "README.md").is_file()
        assert (out_dir / "dataset_infos.json").is_file()
        assert (out_dir / "raw" / "run-a" / "calls.jsonl.gz").is_file()

        turns = load_dataset(str(out_dir), download_mode="force_redownload")["train"]
        system_prompts = load_dataset(
            str(out_dir), "system_prompts", download_mode="force_redownload"
        )["train"]
        toolsets = load_dataset(
            str(out_dir), "toolsets", download_mode="force_redownload"
        )["train"]
        runs = load_dataset(str(out_dir), "runs", download_mode="force_redownload")[
            "train"
        ]

        assert len(turns) == 1
        assert len(system_prompts) == 1
        assert len(toolsets) == 1
        assert len(runs) == 1
        assert json.loads(turns[0]["result"])["success"] is True

        system_by_id = {row["system_prompt_id"]: row for row in system_prompts}
        toolsets_by_id = {row["toolset_id"]: row for row in toolsets}
        restored = reconstruct_request(turns[0], system_by_id, toolsets_by_id)

        assert restored["messages"][0]["content"] == "あなたはエイダです。"
        assert restored["tools"][0]["function"]["name"] == "spot_graph_explore"
        request = json.loads(turns[0]["request"])
        assert request["request_hash"] == compute_request_hash(request["kwargs"])

    def test_multiple_runs_deduplicate_system_prompts_and_toolsets(
        self, tmp_path: Path
    ) -> None:
        """複数 run export では system prompt と toolset を hash id で重複排除する。"""

        run_a = _create_prompt_dataset_run(
            tmp_path,
            run_id="run-a",
            llm_call_id="call-a1",
            system_content="共通 system prompt",
            tool_name="speak",
        )
        run_b = _create_prompt_dataset_run(
            tmp_path,
            run_id="run-b",
            llm_call_id="call-b1",
            system_content="共通 system prompt",
            tool_name="speak",
        )
        out_dir = tmp_path / "dataset_multi"

        summary = export_prompt_dataset(run_dirs=[run_a, run_b], out_dir=out_dir)

        turns = load_dataset(str(out_dir), download_mode="force_redownload")["train"]
        system_prompts = load_dataset(
            str(out_dir), "system_prompts", download_mode="force_redownload"
        )["train"]
        toolsets = load_dataset(
            str(out_dir), "toolsets", download_mode="force_redownload"
        )["train"]

        assert summary.turns_count == 2
        assert len(system_prompts) == 1
        assert len(toolsets) == 1
        assert sorted(row["run_id"] for row in turns) == ["run-a", "run-b"]

    def test_split_map_assigns_runs_without_random_turn_split(
        self, tmp_path: Path
    ) -> None:
        """split-map を渡すと run 単位で train / validation に割り当てる。"""

        run_a = _create_prompt_dataset_run(
            tmp_path,
            run_id="run-a",
            llm_call_id="call-a1",
            system_content="sys-a",
            tool_name="speak",
        )
        run_b = _create_prompt_dataset_run(
            tmp_path,
            run_id="run-b",
            llm_call_id="call-b1",
            system_content="sys-b",
            tool_name="spot_graph_explore",
        )
        split_map = tmp_path / "split.json"
        split_map.write_text(
            json.dumps({"train": ["run-a"], "validation": ["run-b"]}),
            encoding="utf-8",
        )
        out_dir = tmp_path / "dataset_split"

        export_prompt_dataset(
            run_dirs=[run_a, run_b],
            out_dir=out_dir,
            split_map_path=split_map,
        )

        turns = load_dataset(str(out_dir), download_mode="force_redownload")

        assert sorted(turns.keys()) == ["train", "validation"]
        assert turns["train"][0]["run_id"] == "run-a"
        assert turns["validation"][0]["run_id"] == "run-b"

    def test_missing_turn_result_fails_fast(self, tmp_path: Path) -> None:
        """calls に対応する turn_results が無い run は export 時に fail-fast する。"""

        run_dir = _create_prompt_dataset_run(
            tmp_path,
            run_id="run-a",
            llm_call_id="call-a1",
            system_content="sys",
            tool_name="speak",
        )
        (run_dir / "prompt_dataset" / "turn_results.jsonl").write_text(
            "", encoding="utf-8"
        )

        try:
            export_prompt_dataset(run_dirs=[run_dir], out_dir=tmp_path / "dataset_missing")
        except ValueError as exc:
            assert "turn_results.jsonl missing llm_call_id='call-a1'" in str(exc)
        else:
            raise AssertionError("ValueError が発生しなかった")


def _create_prompt_dataset_run(
    tmp_path: Path,
    *,
    run_id: str,
    llm_call_id: str,
    system_content: str,
    tool_name: str,
) -> Path:
    run_dir = tmp_path / run_id
    sink = PromptDatasetCaptureSink(
        run_dir=run_dir,
        run_id=run_id,
        run_metadata={
            "profile": "test",
            "scenario_path": "scenario.json",
            "runtime_config": {"llm_api_key": None},
        },
    )
    context = PromptDatasetCallContext(
        llm_call_id=llm_call_id,
        run_id=run_id,
        world_id=1,
        being_id=f"being_{run_id}",
        player_id=1,
        persona_id="persona:sha256:test",
        character_name="エイダ",
        turn_index=1,
        world_tick=1,
    )
    request_kwargs = {
        "model": "stub",
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "周囲を確認してください。"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": "tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        "tool_choice": "required",
        "max_retries": 0,
    }
    sink.record_call(
        context=context,
        request_kwargs=request_kwargs,
        response={
            "id": llm_call_id,
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": tool_name,
                                    "arguments": "{}",
                                }
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
        output={"name": tool_name, "arguments": {}},
        metrics={"success": True},
    )
    sink.record_turn_result(
        llm_call_id=llm_call_id,
        run_id=run_id,
        world_tick=1,
        player_id=1,
        result={"success": True, "tool": tool_name, "message": "OK"},
    )
    return run_dir
