"""行動のあとの疲労の保存に失敗しても、親の行動は倒さず、失敗を trace とログに残す。

疲労は行動が確定したあとの後処理で、保存に失敗しても行動そのものは戻らない。
これまでは ``except Exception: pass`` で黙って捨てていて、疲労が溜まらない run が
何も起きていない run に見えた。後処理の失敗は design_decisions D1558-2 の入口
(``world_tick_unit_failed``、``continued=True``) で残す。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_WAIT
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
    WorldTickFailureIsolator,
    WorldTickFailurePolicy,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_DRILL = Path(__file__).resolve().parents[5] / "data" / "scenarios" / "station_drill.json"


class _ListRecorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events = []

    def record(self, kind, *, tick=None, player_id=None, **payload):
        event = super().record(kind, tick=tick, player_id=player_id, **payload)
        self.events.append(event)
        return event


def _executor_whose_status_save_fails(monkeypatch):
    runtime = create_world_runtime(_DRILL)
    recorder = _ListRecorder()
    runtime.set_trace_recorder(recorder)
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        llm_client=StubLlmClient(None),
    )
    executor = wiring._spot_graph_executor

    def _broken_save(status):
        raise RuntimeError("status store is down")

    monkeypatch.setattr(executor._player_status_repository, "save", _broken_save)
    return runtime, executor, recorder


class TestFatigueSaveFailure:
    """疲労の保存に失敗したとき、行動を倒さずに失敗を残すことを保証する。"""

    def test_failure_is_recorded_in_the_trace_and_does_not_raise(self, monkeypatch) -> None:
        """保存が例外を出しても例外は親に上がらず、world_tick_unit_failed が 1 件、疲労の段として残る。"""
        _, executor, recorder = _executor_whose_status_save_fails(monkeypatch)

        executor._apply_fatigue_safe(1, 2)

        failures = [e for e in recorder.events if e.kind == TraceEventKind.WORLD_TICK_UNIT_FAILED]
        assert len(failures) == 1
        (failure,) = failures
        assert failure.player_id == 1
        assert failure.payload["stage"] == "action.fatigue"
        assert failure.payload["target_kind"] == "player"
        assert failure.payload["error_type"] == "RuntimeError"
        assert failure.payload["continued"] is True

    def test_recovery_failure_is_recorded_the_same_way(self, monkeypatch) -> None:
        """疲労の回復の保存が例外を出しても、例外は親に上がらず、同じ疲労の段として 1 件残る。"""
        _, executor, recorder = _executor_whose_status_save_fails(monkeypatch)

        executor._recover_fatigue_safe(1, 2)

        failures = [e for e in recorder.events if e.kind == TraceEventKind.WORLD_TICK_UNIT_FAILED]
        assert [f.payload["stage"] for f in failures] == ["action.fatigue"]

    def test_without_a_runtime_the_failure_is_logged(self, monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
        """trace の記録先を持たない実行器 (runtime 無し) では、保存の失敗を WARNING のログに残し、例外は上げない。"""
        _, executor, _ = _executor_whose_status_save_fails(monkeypatch)
        monkeypatch.setattr(executor, "_runtime", None)

        with caplog.at_level(logging.WARNING):
            executor._apply_fatigue_safe(1, 2)

        assert any("fatigue" in record.getMessage() and record.exc_info for record in caplog.records)

    def test_strict_recovery_failure_is_raised_without_recording(self, monkeypatch) -> None:
        """use_item の効果を厳密に扱う設定では、回復の保存の失敗は投げ直し、trace には残さない。"""
        _, executor, recorder = _executor_whose_status_save_fails(monkeypatch)
        monkeypatch.setattr(executor, "_use_item_strict_effects", True, raising=False)

        with pytest.raises(RuntimeError, match="status store is down"):
            executor._recover_fatigue_safe(1, 2)

        assert [e for e in recorder.events if e.kind == TraceEventKind.WORLD_TICK_UNIT_FAILED] == []


class TestFatigueSaveFailureThroughTheTool:
    """ツールの呼び出しを通しても、疲労の保存の失敗が行動を失敗にしないことを保証する。"""

    def test_wait_succeeds_and_the_failure_is_recorded(self, monkeypatch) -> None:
        """疲労の保存が例外を出しても、wait は成功の結果を返し、疲労の段の失敗が 1 件残る。"""
        _, executor, recorder = _executor_whose_status_save_fails(monkeypatch)

        result = executor.get_handlers()[TOOL_NAME_SPOT_GRAPH_WAIT](1, {})

        assert result.success is True
        failures = [e for e in recorder.events if e.kind == TraceEventKind.WORLD_TICK_UNIT_FAILED]
        assert [f.payload["stage"] for f in failures] == ["action.fatigue"]

    def test_under_fail_fast_wait_still_succeeds_and_the_failure_is_recorded(self, monkeypatch) -> None:
        """fail_fast でも、確定済みの wait は成功の結果を返す (失敗を返すと LLM が行動を繰り返す)。疲労の段の失敗は 1 件残る。"""
        runtime, executor, recorder = _executor_whose_status_save_fails(monkeypatch)
        monkeypatch.setattr(
            runtime,
            "_world_tick_failure_isolator",
            WorldTickFailureIsolator(policy=WorldTickFailurePolicy.FAIL_FAST, trace_recorder_provider=lambda: recorder),
        )

        result = executor.get_handlers()[TOOL_NAME_SPOT_GRAPH_WAIT](1, {})

        assert result.success is True
        failures = [e for e in recorder.events if e.kind == TraceEventKind.WORLD_TICK_UNIT_FAILED]
        assert [(f.payload["stage"], f.payload["policy"]) for f in failures] == [("action.fatigue", "fail_fast")]
