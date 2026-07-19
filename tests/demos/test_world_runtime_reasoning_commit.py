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
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
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


def _reasoning_config() -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.for_tests(
        episodic_enabled=True,
        semantic_search_enabled=True,
        belief_evidence_enabled=True,
        belief_consolidation_enabled=True,
        goal_reflect_enabled=True,
        stagnation_pressure_enabled=True,
        stagnation_reasoning_enabled=True,
    )


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


class _RecordingArgsClient:
    """invoke の (tool_choice, 強制指示の有無, reasoning_effort) を記録し成功を返す。"""

    def __init__(self) -> None:
        self.calls: list = []

    def invoke(
        self, messages, tools, choice, *, metrics_sink=None, reasoning_effort=None
    ):
        from ai_rpg_world.application.llm.services.force_tool_call_instruction import (
            FORCE_TOOL_CALL_INSTRUCTION,
        )
        has_instr = any(
            isinstance(m.get("content"), str)
            and FORCE_TOOL_CALL_INSTRUCTION in m["content"]
            for m in messages
        )
        self.calls.append((choice, has_instr, reasoning_effort))
        return {"name": "wait", "arguments": {"reason": "ok"}}


class TestReasoningTurnUsesAutoWithForceInstruction:
    """熟考ターンは tool_choice=auto + 強制指示、通常ターンは required + 指示なし。

    DeepSeek が thinking + required を 400 で拒否するため、熟考ターンだけ auto に
    切替え「必ずツールを呼べ」を末尾に足す。通常ターンは従来どおり required で
    プロンプトも不変 (prefix cache 維持)。
    """

    def test_auto(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """熟考ターンはauto and 強制指示つき。"""
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(
            monkeypatch, tmp_path, stub=None, runtime_config=_reasoning_config()
        )
        client = _RecordingArgsClient()
        state.llm_wiring.llm_client = client
        pid = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))
        being_id = state.runtime.aux_being_resolver.resolve_being_id(
            state.runtime.aux_being_default_world_id, pid
        )
        for _ in range(3):  # band strong
            state.runtime._stagnation_pressure_store.increment_by_being(being_id)
        state.runtime._emit_reflect_observation(pid, "空回りしている", "stalled")

        state.llm_wiring.run_phase_a(pid)

        assert client.calls == [("auto", True, "low")]

    def test_required(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """通常ターンはrequired and 指示なし。"""
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(
            monkeypatch, tmp_path, stub=None, runtime_config=_reasoning_config()
        )
        client = _RecordingArgsClient()
        state.llm_wiring.llm_client = client
        pid = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))
        # ラッチを arm しない → 熟考しない通常ターン
        state.llm_wiring.run_phase_a(pid)

        assert client.calls == [("required", False, None)]


class TestReasoningStarvationFallback:
    """熟考ターンの invoke が失敗したら latch を消費し reasoning なしで降格再試行する。

    これをしないと、詰まった (band=strong) agent が毎行動 same-condition で失敗し
    続けて餓死する (実 run v3coop_stagnation_002 で P3 が tick42 以降 38 連続失敗)。
    """

    def _armed_session(self, monkeypatch, tmp_path, client):
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(
            monkeypatch, tmp_path, stub=None, runtime_config=_reasoning_config()
        )
        state.llm_wiring.llm_client = client
        rec = _CapturingTraceRecorder()
        state.runtime.set_trace_recorder(rec)
        pid = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))
        being_id = state.runtime.aux_being_resolver.resolve_being_id(
            state.runtime.aux_being_default_world_id, pid
        )
        for _ in range(3):
            state.runtime._stagnation_pressure_store.increment_by_being(being_id)
        state.runtime._emit_reflect_observation(pid, "空回りしている", "stalled")
        return state, rec, pid

    def test_invoke_reasoning_raises_exception(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """熟考invokeが例外なら reasoningなしで降格再試行して行動成立。"""
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

    def test_tool_call_reasoning_line(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """熟考ターンがtool callなしでも reasoningなしで降格再試行。"""
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

    def test_tool_call_latch_engaged_trace(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """熟考も降格もNO TOOL CALLなら latch消費 engaged traceなし。"""
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(
            monkeypatch, tmp_path, stub=None, runtime_config=_reasoning_config()
        )
        # 熟考でも降格でも常に None (NO_TOOL_CALL) を返す
        client = _NoToolCallClient()
        state.llm_wiring.llm_client = client
        rec = _CapturingTraceRecorder()
        state.runtime.set_trace_recorder(rec)

        pid = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))
        being_id = state.runtime.aux_being_resolver.resolve_being_id(
            state.runtime.aux_being_default_world_id, pid
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
