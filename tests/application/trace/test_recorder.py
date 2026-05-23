"""TraceRecorder と TraceEvent の挙動テスト (Issue #188 Phase 1d)。"""

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.trace.events import TraceEvent, TraceEventKind
from ai_rpg_world.application.trace.recorder import (
    JsonlTraceRecorder,
    NullTraceRecorder,
    load_trace_events,
)


class TestTraceEvent:
    """TraceEvent の dict 化往復。"""

    def test_to_jsonable_と_from_jsonable_が往復可能(self) -> None:
        """JSON シリアライズ可能な dict と TraceEvent を相互変換できる。"""
        event = TraceEvent(
            seq=1,
            timestamp="2026-05-24T03:00:00+00:00",
            kind=TraceEventKind.OBSERVATION,
            tick=5,
            player_id=2,
            payload={"prose": "扉が開いた音がした"},
        )
        restored = TraceEvent.from_jsonable(event.to_jsonable())
        assert restored == event

    def test_from_jsonable_は_dict_以外で_TypeError(self) -> None:
        """非 dict が来たら TypeError。"""
        with pytest.raises(TypeError):
            TraceEvent.from_jsonable("not-a-dict")  # type: ignore[arg-type]


class TestNullTraceRecorder:
    """no-op recorder の seq 振り挙動。"""

    def test_record_は_seq_だけ進めて何も書かない(self) -> None:
        """ファイル書き出しなく seq だけ単調増加する。"""
        rec = NullTraceRecorder()
        e1 = rec.record(TraceEventKind.NOTE, tick=1, player_id=1, message="hi")
        e2 = rec.record(TraceEventKind.NOTE, tick=2)
        assert e1.seq == 1
        assert e2.seq == 2
        assert e2.tick == 2
        # close は no-op
        rec.close()


class TestJsonlTraceRecorder:
    """JSONL 出力 recorder の整形と読み戻し。"""

    def test_記録した_event_が_JSONL_に_1_行ずつ書かれる(self, tmp_path: Path) -> None:
        """record() 呼び出しごとに 1 行 (JSON) が append される。"""
        path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(path) as rec:
            rec.record(TraceEventKind.RUN_START, run_id="exp-01")
            rec.record(
                TraceEventKind.OBSERVATION,
                tick=3,
                player_id=1,
                prose="扉が軋む",
            )
            rec.record(TraceEventKind.MEMO_ADD, tick=3, player_id=1, memo_id="m1")

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        first = json.loads(lines[0])
        assert first["kind"] == TraceEventKind.RUN_START
        assert first["payload"] == {"run_id": "exp-01"}

    def test_load_trace_events_で_書いた_event_を読み戻せる(self, tmp_path: Path) -> None:
        """JSONL 読み込みジェネレータが seq 順で TraceEvent を返す。"""
        path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(path) as rec:
            rec.record(TraceEventKind.ACTION, tick=1, player_id=1, tool="press")
            rec.record(TraceEventKind.ACTION_RESULT, tick=1, player_id=1, success=True)

        events = list(load_trace_events(path))
        assert [e.seq for e in events] == [1, 2]
        assert events[0].kind == TraceEventKind.ACTION
        assert events[1].payload == {"success": True}

    def test_close_後の_record_は_RuntimeError(self, tmp_path: Path) -> None:
        """close 済み recorder で record すると RuntimeError。"""
        path = tmp_path / "trace.jsonl"
        rec = JsonlTraceRecorder(path)
        rec.close()
        with pytest.raises(RuntimeError):
            rec.record(TraceEventKind.NOTE)

    def test_path_引数が_Path_でなければ_TypeError(self) -> None:
        """path に str が来たら TypeError。"""
        with pytest.raises(TypeError):
            JsonlTraceRecorder("/tmp/trace.jsonl")  # type: ignore[arg-type]

    def test_seq_は_1_から始まり単調増加する(self, tmp_path: Path) -> None:
        """recorder の seq は 1 から始まり各 record で 1 増える。"""
        path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(path) as rec:
            e1 = rec.record(TraceEventKind.TICK_START, tick=0)
            e2 = rec.record(TraceEventKind.TICK_END, tick=0)
        assert (e1.seq, e2.seq) == (1, 2)
