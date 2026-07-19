"""MemoToolExecutor が trace_recorder に memo_add / memo_done を自動 record するか確認。

Phase 3 Step 3a-3: Resolver+WorldId 必須 + provision 済 Being を前提に書換。
"""

from typing import List

from ai_rpg_world.application.llm.services.executors.memo_executor import (
    MemoToolExecutor,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
)
from ai_rpg_world.application.trace import TraceEvent, TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from tests.application.llm._memo_being_test_helpers import (
    make_memo_being_setup,
)


class _CapturingRecorder(ITraceRecorder):
    def __init__(self) -> None:
        self._seq = 0
        self.events: List[TraceEvent] = []

    def record(self, kind, *, tick=None, player_id=None, **payload):
        self._seq += 1
        ev = TraceEvent(
            seq=self._seq,
            timestamp="2026-01-01T00:00:00+00:00",
            kind=str(kind),
            tick=tick,
            player_id=player_id,
            payload=dict(payload),
        )
        self.events.append(ev)
        return ev

    def close(self) -> None:
        pass


class TestMemoExecutorTraceRecording:
    """MemoToolExecutor の trace 統合挙動。"""

    def test_records_memo_add_success_memo_add_event(self) -> None:
        """memo_add 実行成功時に trace.record(MEMO_ADD) が呼ばれる。"""
        setup = make_memo_being_setup()
        setup.provision(1)
        rec = _CapturingRecorder()
        exec_ = MemoToolExecutor(
            setup.memo_store,
            current_tick_provider=lambda: 4,
            trace_recorder=rec,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        handlers = exec_.get_handlers()
        result = handlers[TOOL_NAME_MEMO_ADD](1, {"content": "扉固定スイッチを押す"})
        assert result.success
        assert len(rec.events) == 1
        ev = rec.events[0]
        assert ev.kind == TraceEventKind.MEMO_ADD
        assert ev.tick == 4
        assert ev.player_id == 1
        assert ev.payload["content"] == "扉固定スイッチを押す"
        assert "memo_id" in ev.payload

    def test_records_memo_done_success_memo_done_event(self) -> None:
        """memo_done で完了したときに trace.record(MEMO_DONE) が呼ばれる。"""
        setup = make_memo_being_setup()
        being_id = setup.provision(1)
        memo_id = setup.memo_store.add_by_being(being_id, "x")
        rec = _CapturingRecorder()
        exec_ = MemoToolExecutor(
            setup.memo_store,
            current_tick_provider=lambda: 9,
            trace_recorder=rec,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        handlers = exec_.get_handlers()
        result = handlers[TOOL_NAME_MEMO_DONE](1, {"memo_ids": [memo_id]})
        assert result.success
        assert any(
            e.kind == TraceEventKind.MEMO_DONE and e.payload.get("memo_id") == memo_id
            for e in rec.events
        )

    def test_memo_done_failure_memo_done_event(self) -> None:
        """memo_id が存在しない時は MEMO_DONE event を出さない。"""
        setup = make_memo_being_setup()
        setup.provision(1)
        rec = _CapturingRecorder()
        exec_ = MemoToolExecutor(
            setup.memo_store,
            trace_recorder=rec,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        handlers = exec_.get_handlers()
        result = handlers[TOOL_NAME_MEMO_DONE](1, {"memo_ids": ["non-existent"]})
        assert not result.success
        assert not any(e.kind == TraceEventKind.MEMO_DONE for e in rec.events)

    def test_trace_recorder_uninjected_does_not_crash(self) -> None:
        """trace_recorder=None でも MemoToolExecutor は通常動作する。"""
        setup = make_memo_being_setup()
        setup.provision(1)
        exec_ = MemoToolExecutor(
            setup.memo_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        handlers = exec_.get_handlers()
        result = handlers[TOOL_NAME_MEMO_ADD](1, {"content": "x"})
        assert result.success
