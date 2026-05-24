"""MemoToolExecutor が trace_recorder に memo_add / memo_done を自動 record するか確認。"""

from typing import List

from ai_rpg_world.application.llm.services.executors.memo_executor import (
    MemoToolExecutor,
)
from ai_rpg_world.application.llm.services.in_memory_memo_store import (
    InMemoryMemoStore,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
)
from ai_rpg_world.application.trace import TraceEvent, TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder


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

    def test_memo_add_成功時に_MEMO_ADD_イベントを記録する(self) -> None:
        """memo_add 実行成功時に trace.record(MEMO_ADD) が呼ばれる。"""
        store = InMemoryMemoStore()
        rec = _CapturingRecorder()
        exec_ = MemoToolExecutor(
            store,
            current_tick_provider=lambda: 4,
            trace_recorder=rec,
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

    def test_memo_done_成功時に_MEMO_DONE_イベントを記録する(self) -> None:
        """memo_done で完了したときに trace.record(MEMO_DONE) が呼ばれる。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        store = InMemoryMemoStore()
        memo_id = store.add(PlayerId(1), "x")
        rec = _CapturingRecorder()
        exec_ = MemoToolExecutor(
            store,
            current_tick_provider=lambda: 9,
            trace_recorder=rec,
        )
        handlers = exec_.get_handlers()
        result = handlers[TOOL_NAME_MEMO_DONE](1, {"memo_id": memo_id})
        assert result.success
        assert any(
            e.kind == TraceEventKind.MEMO_DONE and e.payload.get("memo_id") == memo_id
            for e in rec.events
        )

    def test_memo_done_失敗時は_MEMO_DONE_イベントを記録しない(self) -> None:
        """memo_id が存在しない時は MEMO_DONE event を出さない。"""
        store = InMemoryMemoStore()
        rec = _CapturingRecorder()
        exec_ = MemoToolExecutor(store, trace_recorder=rec)
        handlers = exec_.get_handlers()
        result = handlers[TOOL_NAME_MEMO_DONE](1, {"memo_id": "non-existent"})
        assert not result.success
        assert not any(e.kind == TraceEventKind.MEMO_DONE for e in rec.events)

    def test_trace_recorder_未注入でもクラッシュしない(self) -> None:
        """trace_recorder=None でも MemoToolExecutor は通常動作する。"""
        store = InMemoryMemoStore()
        exec_ = MemoToolExecutor(store)
        handlers = exec_.get_handlers()
        result = handlers[TOOL_NAME_MEMO_ADD](1, {"content": "x"})
        assert result.success
