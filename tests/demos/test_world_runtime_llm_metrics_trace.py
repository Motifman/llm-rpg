"""run_phase_a で LLM 呼び出しの metrics が trace_recorder に流れることを検証。

invoke が metrics_sink を受け取り、LLM_CALL event が record される。
trace_recorder 未注入の経路では sink=None なので no-op (litellm 側はクラッシュしない)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.llm_call_metrics import LlmCallMetrics
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _CapturingTraceRecorder:
    """trace.record を呼ばれた kind+payload の list で受ける単純な fake。"""

    def __init__(self) -> None:
        self.records: list = []

    def record(self, kind: str, **kwargs: Any) -> None:
        self.records.append((kind, dict(kwargs)))


class _FakeLlmClient:
    """metrics_sink を受け取り、固定値で record する fake LLM。"""

    def __init__(self) -> None:
        self.last_sink: Any = None

    def invoke(
        self, messages, tools, choice, *, metrics_sink=None, reasoning_effort=None
    ) -> dict:
        self.last_sink = metrics_sink
        if metrics_sink is not None:
            metrics_sink.record(LlmCallMetrics(
                model="fake/model",
                wall_latency_ms=1234,
                prompt_tokens=100,
                completion_tokens=42,
                tps=34.0,
                success=True,
                error_code=None,
            ))
        return {"name": "wait", "arguments": {"reason": "test"}}


class TestPhaseAMetricsSink:
    """Phase A 経由で LLM_CALL trace event が記録される。"""

    def test_trace_recorder_があると_LLM_CALL_event_が_記録される(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        state.llm_wiring.llm_client = _FakeLlmClient()
        # runtime に trace_recorder を後付け注入 (runtime_manager は
        # getattr(self.runtime, "trace_recorder", None) で参照する)
        rec = _CapturingTraceRecorder()
        state.runtime.set_trace_recorder(rec)

        pid = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))
        state.llm_wiring.run_phase_a(pid)

        llm_call_records = [
            (kind, payload) for kind, payload in rec.records
            if kind == TraceEventKind.LLM_CALL
        ]
        assert len(llm_call_records) == 1, (
            f"LLM_CALL trace event が記録されていない (記録: {rec.records})"
        )
        _, payload = llm_call_records[0]
        assert payload["model"] == "fake/model"
        assert payload["wall_latency_ms"] == 1234
        assert payload["prompt_tokens"] == 100
        assert payload["completion_tokens"] == 42
        assert payload["tps"] == 34.0
        assert payload["success"] is True
        assert payload["player_id"] == pid.value

    def test_tick_は_sink_record_時点で_取得される(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """Review HIGH 2 対応: sink 構築時の固定 tick ではなく record 時の tick を使う。

        遅い LLM 呼び出しが tick 境界を跨いだ場合に stale tick で記録されない
        ことを保証する。
        """
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        class _TickAdvancingClient:
            """invoke のたびに runtime の tick を 1 進める stub。
            sink construction が record より前なら、旧コードでは tick がずれる。
            """
            def __init__(self, runtime):
                self.runtime = runtime

            def invoke(self, messages, tools, choice, *, metrics_sink=None, reasoning_effort=None) -> dict:
                # 呼び出し中に tick を 1 進める (= LLM call が tick boundary を跨ぐ)
                self.runtime.advance_tick()
                if metrics_sink is not None:
                    metrics_sink.record(LlmCallMetrics(
                        model="fake/model",
                        wall_latency_ms=100,
                        prompt_tokens=10, completion_tokens=5,
                        tps=50.0, success=True, error_code=None,
                    ))
                return {"name": "wait", "arguments": {"reason": "test"}}

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        state.llm_wiring.llm_client = _TickAdvancingClient(state.runtime)
        rec = _CapturingTraceRecorder()
        state.runtime.set_trace_recorder(rec)
        tick_before = int(state.runtime.current_tick())

        pid = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))
        state.llm_wiring.run_phase_a(pid)

        llm_call_records = [
            (kind, payload) for kind, payload in rec.records
            if kind == TraceEventKind.LLM_CALL
        ]
        assert len(llm_call_records) == 1
        _, payload = llm_call_records[0]
        # tick は invoke 後の値 (= tick_before + 1) になっているはず。
        # 旧コード (sink 構築時に capture) だと tick_before のままで失敗する。
        assert payload["tick"] == tick_before + 1, (
            f"sink.record() 時点の tick ({tick_before + 1}) ではなく "
            f"sink 構築時の tick ({tick_before}) が記録された (= stale)"
        )

    def test_trace_recorder_が_None_なら_sink_は_None(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        client = _FakeLlmClient()
        state.llm_wiring.llm_client = client
        # trace_recorder 未注入 (default は None) — session 作成直後の状態

        pid = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))
        state.llm_wiring.run_phase_a(pid)

        assert client.last_sink is None, "sink が None でないと litellm が record を呼んでしまう"
