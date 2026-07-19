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
        self.calls: list = []

    def invoke(
        self, messages, tools, choice, *, metrics_sink=None, reasoning_effort=None
    ) -> None:
        self.last_reasoning_effort = reasoning_effort
        self.calls.append(reasoning_effort)
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


class _ReasoningFailThenFallbackClient:
    """熟考付き (reasoning_effort != None) 呼び出しは失敗し、reasoning なしの
    降格呼び出しは成功する fake。餓死ループ修正の検証用。

    fail_mode="raise": 熟考 call は例外 (実 run の 400 相当)。
    fail_mode="none":  熟考 call は tool_call なし (None) で返る。
    """

    def __init__(self, fail_mode: str = "raise") -> None:
        self.fail_mode = fail_mode
        self.calls: list = []  # 各呼び出しの reasoning_effort を順に記録

    def invoke(
        self, messages, tools, choice, *, metrics_sink=None, reasoning_effort=None
    ):
        self.calls.append(reasoning_effort)
        if reasoning_effort is not None:
            # 熟考ターン: 失敗する
            if metrics_sink is not None:
                metrics_sink.record(LlmCallMetrics(
                    model="fake/model", wall_latency_ms=10,
                    prompt_tokens=10, completion_tokens=0, tps=0.0,
                    success=False, error_code="LLM_API_CALL_FAILED",
                ))
            if self.fail_mode == "raise":
                raise RuntimeError("Thinking mode does not support this tool_choice")
            return None
        # reasoning なしの降格呼び出し: 成功して行動を成立させる
        if metrics_sink is not None:
            metrics_sink.record(LlmCallMetrics(
                model="fake/model", wall_latency_ms=10,
                prompt_tokens=10, completion_tokens=5, tps=5.0,
                success=True, error_code=None,
            ))
        return {"name": "wait", "arguments": {"reason": "fallback"}}


class TestReasoningStarvationFallback:
    """熟考ターンの invoke が失敗したら latch を消費し reasoning なしで降格再試行する。

    これをしないと、詰まった (band=strong) agent が毎行動 same-condition で失敗し
    続けて餓死する (実 run v3coop_stagnation_002 で P3 が tick42 以降 38 連続失敗)。
    """

    def _armed_session(self, monkeypatch, tmp_path, client):
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        _enable_reasoning_prereqs(monkeypatch)
        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        state.llm_wiring.llm_client = client
        rec = _CapturingTraceRecorder()
        state.runtime.set_trace_recorder(rec)
        pid = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))
        being_id = state.runtime._aux_being_resolver.resolve_being_id(
            state.runtime._aux_being_default_world_id, pid
        )
        for _ in range(3):
            state.runtime._stagnation_pressure_store.increment_by_being(being_id)
        state.runtime._emit_reflect_observation(pid, "空回りしている", "stalled")
        return state, rec, pid

    def test_熟考invokeが例外なら_reasoningなしで降格再試行して行動成立(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        client = _ReasoningFailThenFallbackClient(fail_mode="raise")
        state, rec, pid = self._armed_session(monkeypatch, tmp_path, client)

        res = state.llm_wiring.run_phase_a(pid)

        # 1 回目 low で失敗 → 2 回目 None (降格) で成立
        assert client.calls == ["low", None]
        assert res.tool_call == {"name": "wait", "arguments": {"reason": "fallback"}}
        assert res.exception is None
        # latch は消費済み = 次行動で同条件リトライしない (餓死しない)
        assert state.runtime._stagnation_reasoning_latch.is_armed(pid) is False
        # 熟考は実行成立していないので engaged trace は出ない
        engaged = [
            k for k, _ in rec.records if k == TraceEventKind.AGENT_REASONING_ENGAGED
        ]
        assert engaged == []

    def test_熟考ターンがtool_callなしでも_reasoningなしで降格再試行(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        client = _ReasoningFailThenFallbackClient(fail_mode="none")
        state, rec, pid = self._armed_session(monkeypatch, tmp_path, client)

        res = state.llm_wiring.run_phase_a(pid)

        assert client.calls == ["low", None]
        assert res.tool_call == {"name": "wait", "arguments": {"reason": "fallback"}}
        assert state.runtime._stagnation_reasoning_latch.is_armed(pid) is False
        engaged = [
            k for k, _ in rec.records if k == TraceEventKind.AGENT_REASONING_ENGAGED
        ]
        assert engaged == []


class TestReasoningCommitOnNoToolCall:
    """熟考ターンが NO_TOOL_CALL のとき commit も engaged trace もされない。

    餓死ループ修正後: NO_TOOL_CALL は reasoning なし降格再試行を起こす。降格後も
    tool_call が返らなければ行動は不成立だが、latch は消費済み (次行動で同条件
    リトライしない = 餓死しない) で、AGENT_REASONING_ENGAGED trace も出ない。
    """

    def test_熟考も降格もNO_TOOL_CALLなら_latch消費_engaged_traceなし(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        _enable_reasoning_prereqs(monkeypatch)
        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        # 熟考でも降格でも常に None (NO_TOOL_CALL) を返す
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

        res = state.llm_wiring.run_phase_a(pid)

        # 熟考 (low) → NO_TOOL_CALL → 降格 (None) の 2 回呼ばれる
        assert client.calls == ["low", None]
        assert res.tool_call is None  # 降格後も NO_TOOL_CALL = 行動不成立
        # latch は消費済み = 次行動で同条件リトライしない (餓死しない)
        assert state.runtime._stagnation_reasoning_latch.is_armed(pid) is False
        # 行動が成立していないので engaged trace は出ない
        engaged = [
            (kind, payload) for kind, payload in rec.records
            if kind == TraceEventKind.AGENT_REASONING_ENGAGED
        ]
        assert engaged == []
