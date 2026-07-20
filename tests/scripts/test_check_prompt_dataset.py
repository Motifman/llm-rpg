"""scripts/check_prompt_dataset.py の prompt dataset 品質検査を保証する。"""

from __future__ import annotations

import json
from pathlib import Path

from ai_rpg_world.application.llm.services.prompt_dataset_capture import (
    PromptDatasetCallContext,
    PromptDatasetCaptureSink,
)
from scripts.check_prompt_dataset import check_prompt_dataset


class TestCheckPromptDataset:
    """prompt_dataset raw capture と trace の整合性検査仕様。"""

    def test_valid_run_passes_all_checks(self, tmp_path: Path) -> None:
        """calls / turn_results / sidecar / trace / capture_status が揃う run は成功する。"""

        run_dir = _create_run(tmp_path, run_id="run-a", llm_call_id="call-a")

        result = check_prompt_dataset(run_dirs=[run_dir])

        assert result.ok is True
        assert result.errors == []
        assert result.summary["runs_count"] == 1
        assert result.summary["calls_count"] == 1

    def test_trace_llm_call_count_mismatch_fails(self, tmp_path: Path) -> None:
        """trace.jsonl の llm_call 件数が calls 件数と違う run は失敗する。"""

        run_dir = _create_run(tmp_path, run_id="run-a", llm_call_id="call-a")
        _write_jsonl(run_dir / "trace.jsonl", [])

        result = check_prompt_dataset(run_dirs=[run_dir])

        assert result.ok is False
        assert any("trace llm_call count mismatch" in error for error in result.errors)

    def test_turn_result_reference_mismatch_fails(self, tmp_path: Path) -> None:
        """calls と turn_results の llm_call_id が一致しない run は失敗する。"""

        run_dir = _create_run(tmp_path, run_id="run-a", llm_call_id="call-a")
        dataset_dir = run_dir / "prompt_dataset"
        _write_jsonl(
            dataset_dir / "turn_results.jsonl",
            [
                {
                    "schema_version": 1,
                    "llm_call_id": "orphan-call",
                    "run_id": "run-a",
                    "world_tick": 1,
                    "player_id": 1,
                    "result": {"success": True},
                    "trace_refs": {},
                }
            ],
        )

        result = check_prompt_dataset(run_dirs=[run_dir])

        assert result.ok is False
        assert any("missing turn_result" in error for error in result.errors)
        assert any("orphan turn_result" in error for error in result.errors)

    def test_system_prompt_and_toolset_reference_mismatch_fails(
        self, tmp_path: Path
    ) -> None:
        """call が参照する system_prompt_id / toolset_id の sidecar が無い run は失敗する。"""

        run_dir = _create_run(tmp_path, run_id="run-a", llm_call_id="call-a")
        dataset_dir = run_dir / "prompt_dataset"
        _write_jsonl(dataset_dir / "system_prompts.jsonl", [])
        _write_jsonl(dataset_dir / "toolsets.jsonl", [])

        result = check_prompt_dataset(run_dirs=[run_dir])

        assert result.ok is False
        assert any("missing system_prompt" in error for error in result.errors)
        assert any("missing toolset" in error for error in result.errors)

    def test_capture_incomplete_true_fails(self, tmp_path: Path) -> None:
        """capture_status が incomplete を示す run は失敗する。"""

        run_dir = _create_run(tmp_path, run_id="run-a", llm_call_id="call-a")
        (run_dir / "prompt_dataset" / "capture_status.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": "run-a",
                    "capture_incomplete": True,
                }
            ),
            encoding="utf-8",
        )

        result = check_prompt_dataset(run_dirs=[run_dir])

        assert result.ok is False
        assert any("capture_incomplete must be false" in error for error in result.errors)

    def test_split_map_must_assign_each_run_once(self, tmp_path: Path) -> None:
        """split-map は run_id を run 単位で過不足なく 1 split にだけ割り当てる。"""

        run_a = _create_run(tmp_path, run_id="run-a", llm_call_id="call-a")
        run_b = _create_run(tmp_path, run_id="run-b", llm_call_id="call-b")
        split_map = tmp_path / "split.json"
        split_map.write_text(
            json.dumps({"train": ["run-a", "unknown"], "validation": ["run-a"]}),
            encoding="utf-8",
        )

        result = check_prompt_dataset(
            run_dirs=[run_a, run_b],
            split_map_path=split_map,
        )

        assert result.ok is False
        assert any("run_id 'run-a' appears in multiple splits" in error for error in result.errors)
        assert any("split-map contains unknown run_id 'unknown'" in error for error in result.errors)
        assert any("run_id 'run-b' is missing from split-map" in error for error in result.errors)


def _create_run(tmp_path: Path, *, run_id: str, llm_call_id: str) -> Path:
    run_dir = tmp_path / run_id
    sink = PromptDatasetCaptureSink(
        run_dir=run_dir,
        run_id=run_id,
        run_metadata={"profile": "test"},
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
    sink.record_call(
        context=context,
        request_kwargs={
            "model": "stub",
            "messages": [
                {"role": "system", "content": "あなたはエイダです。"},
                {"role": "user", "content": "周囲を確認してください。"},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "speak",
                        "description": "話す",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "tool_choice": "required",
            "max_retries": 0,
        },
        response={
            "id": llm_call_id,
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"function": {"name": "speak", "arguments": "{}"}}
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
        output={"name": "speak", "arguments": {}},
        metrics={"success": True},
    )
    sink.record_turn_result(
        llm_call_id=llm_call_id,
        run_id=run_id,
        world_tick=1,
        player_id=1,
        result={"success": True},
    )
    _write_jsonl(
        run_dir / "trace.jsonl",
        [{"kind": "llm_call", "tick": 1, "payload": {"llm_call_id": llm_call_id}}],
    )
    return run_dir


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
