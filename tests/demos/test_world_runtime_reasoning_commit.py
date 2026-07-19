"""案A HIGH 2 の残存偽陽性 (NO_TOOL_CALL 経路) を run_phase_a で塞ぐことを固定する。

LiteLLMClient.invoke は tool_call が取れないとき例外ではなく ``None`` を返す
(error_code="NO_TOOL_CALL")。commit 条件が「invoke が例外を投げなかった」だけだと、
熟考を焚くと決めた行動が NO_TOOL_CALL (行動不成立) になっても、ラッチ消費 +
AGENT_REASONING_ENGAGED trace を出してしまい「熟考したのに行動していない」偽陽性
になる。run_phase_a は tool_call が実際に返ったときだけ commit する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.llm.contracts.llm_call_metrics import LlmCallMetrics
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _CapturingTraceRecorder:
    def __init__(self) -> None:
        self.records: list = []

    def record(self, kind: str, **kwargs: Any) -> None:
        self.records.append((kind, dict(kwargs)))


class _NoToolCallClient:
    """tool_call を返さない (NO_TOOL_CALL) 経路を模す fake。例外は投げない。"""

    def __init__(self) -> None:
        self.last_reasoning_effort: Any = "UNSET"

    def invoke(
        self, messages, tools, choice, *, metrics_sink=None, reasoning_effort=None
    ) -> None:
        self.last_reasoning_effort = reasoning_effort
        if metrics_sink is not None:
            # 実 LiteLLMClient は NO_TOOL_CALL でも metrics を正常に record してから
            # None を返す (例外は投げない)。fake もその契約を守る (tps 必須なので
            # 0.0 を渡す。ここを欠くと record が例外を投げ、run_phase_a の except
            # 経路に落ちて「tool_call=None の commit スキップ」ではなく「例外の
            # commit スキップ」を誤って検証する false-green になる)。
            metrics_sink.record(LlmCallMetrics(
                model="fake/model",
                wall_latency_ms=10,
                prompt_tokens=10,
                completion_tokens=0,
                tps=0.0,
                success=False,
                error_code="NO_TOOL_CALL",
            ))
        return None


def _enable_reasoning_prereqs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("SEMANTIC_SEARCH_ENABLED", "1")
    monkeypatch.setenv("BELIEF_CONSOLIDATION_ENABLED", "1")
    monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
    monkeypatch.setenv("STAGNATION_PRESSURE_ENABLED", "1")
    monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")


class TestReasoningCommitOnNoToolCall:
    """NO_TOOL_CALL のとき、熟考の決定はされてもラッチ消費・trace は起きない。"""

    def test_no_tool_call時は_ラッチ消費もengaged_traceもしない(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        _enable_reasoning_prereqs(monkeypatch)
        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        client = _NoToolCallClient()
        state.llm_wiring.llm_client = client
        rec = _CapturingTraceRecorder()
        state.runtime.set_trace_recorder(rec)

        pid = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))
        being_id = state.runtime._aux_being_resolver.resolve_being_id(
            state.runtime._aux_being_default_world_id, pid
        )
        assert being_id is not None
        for _ in range(3):  # band を strong にする
            state.runtime._stagnation_pressure_store.increment_by_being(being_id)
        # 停滞注入 = ラッチ武装
        state.runtime._emit_reflect_observation(pid, "同じ場所を空回りしている", "stalled")

        state.llm_wiring.run_phase_a(pid)

        # 熟考の決定自体は行われた (effort が invoke に渡っている)
        assert client.last_reasoning_effort == "low"
        # だが NO_TOOL_CALL なので commit されない: ラッチは armed のまま
        assert state.runtime._stagnation_reasoning_latch.is_armed(pid) is True
        # AGENT_REASONING_ENGAGED trace も出ない (行動が成立していないため)
        engaged = [
            (kind, payload) for kind, payload in rec.records
            if kind == TraceEventKind.AGENT_REASONING_ENGAGED
        ]
        assert engaged == []
