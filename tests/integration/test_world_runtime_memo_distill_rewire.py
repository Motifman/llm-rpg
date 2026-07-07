"""U5 (MEMO_DISTILL) の配線が executor 作り直しで失われないことを固定する。

回帰対象の silent failure: ``create_world_runtime`` は memo_distill transcriber
を ``_todo_tool_executor`` に setter 注入していたが、``set_trace_recorder``
(実験 run が build 後に必ず呼ぶ) が ``_todo_tool_executor`` を作り直すため、
transcriber が静かに失われ、実験 run で memo_done があっても MEMO_DISTILL
evidence が 0 件になっていた。

修正: transcriber を ``runtime._memo_distill_transcriber`` に保持し、
``_wire_auxiliary_tool_stack`` が executor を作り直すたびに再適用する。

LLM は呼ばない (stub client)。flag は default OFF なので明示的に ON にする。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.trace import NullTraceRecorder
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _enable_memo_distill_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    # MEMO_DISTILL の transcriber が構築される前提: episodic + 証拠 buffer (U2)。
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("BELIEF_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("MEMO_DISTILL_ENABLED", "1")


class TestWorldRuntimeMemoDistillRewire:
    def test_transcriber_wired_after_build(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_memo_distill_flags(monkeypatch)
        runtime = create_world_runtime(_SCENARIO_PATH)
        assert runtime._memo_distill_transcriber is not None
        assert runtime._todo_tool_executor is not None
        # memo executor 実体にも届いている。
        assert runtime._todo_tool_executor._memo_distill_transcriber is not None

    def test_transcriber_survives_set_trace_recorder_rebuild(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """set_trace_recorder は _todo_tool_executor を作り直すが、

        memo_distill transcriber は再適用されて生き残る (回帰の核心)。"""
        _enable_memo_distill_flags(monkeypatch)
        runtime = create_world_runtime(_SCENARIO_PATH)
        executor_before = runtime._todo_tool_executor
        assert executor_before is not None
        assert executor_before._memo_distill_transcriber is not None

        # 実験 run と同じく build 後に trace recorder を差し込む → 作り直し。
        runtime.set_trace_recorder(NullTraceRecorder())

        executor_after = runtime._todo_tool_executor
        assert executor_after is not None
        # 作り直しで別インスタンスになっている (前提の確認)。
        assert executor_after is not executor_before
        # それでも transcriber は再適用されている (修正が効いている)。
        assert executor_after._memo_distill_transcriber is not None

    def test_flag_off_keeps_transcriber_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.delenv("MEMO_DISTILL_ENABLED", raising=False)
        runtime = create_world_runtime(_SCENARIO_PATH)
        assert runtime._memo_distill_transcriber is None
        if runtime._todo_tool_executor is not None:
            assert runtime._todo_tool_executor._memo_distill_transcriber is None
