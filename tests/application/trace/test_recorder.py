# Phase 3 Step 3e-3 bulk migration: episode_store の player_id 経路撤去に
# 伴い、本ファイルの ``being_id`` 参照を deterministic な ``BeingId`` の
# 既定値で受ける (= テスト内で異なる player_id を使う箇所は個別に上書き)。
# BeingProvisioningService は ``being_w<world>_p<player>`` 形式を使う。
from ai_rpg_world.domain.being.value_object.being_id import BeingId as _MIG_BeingId

being_id = _MIG_BeingId('being_w1_p1')
'TraceRecorder と TraceEvent の挙動テスト (Issue #188 Phase 1d)。'
import json
from pathlib import Path

import pytest

from ai_rpg_world.application.trace.events import TraceEvent, TraceEventKind
from ai_rpg_world.application.trace.recorder import JsonlTraceRecorder, NullTraceRecorder, load_trace_events


class TestTraceEvent:
    """TraceEvent の dict 化往復。"""

    def test_jsonable_round_trips(self) -> None:
        """JSON シリアライズ可能な dict と TraceEvent を相互変換できる。"""
        event = TraceEvent(seq=1, timestamp='2026-05-24T03:00:00+00:00', kind=TraceEventKind.OBSERVATION, tick=5, player_id=2, payload={'prose': '扉が開いた音がした'})
        restored = TraceEvent.from_jsonable(event.to_jsonable())
        assert restored == event

    def test_from_jsonable_dict_raises_type_error(self) -> None:
        """非 dict が来たら TypeError。"""
        with pytest.raises(TypeError):
            TraceEvent.from_jsonable('not-a-dict')

class TestNullTraceRecorder:
    """no-op recorder の seq 振り挙動。"""

    def test_record_seq(self) -> None:
        """ファイル書き出しなく seq だけ単調増加する。"""
        rec = NullTraceRecorder()
        e1 = rec.record(TraceEventKind.NOTE, tick=1, player_id=1, message='hi')
        e2 = rec.record(TraceEventKind.NOTE, tick=2)
        assert e1.seq == 1
        assert e2.seq == 2
        assert e2.tick == 2
        rec.close()

class TestJsonlTraceRecorder:
    """JSONL 出力 recorder の整形と読み戻し。"""

    def test_event_jsonl_one_line_written(self, tmp_path: Path) -> None:
        """record() 呼び出しごとに 1 行 (JSON) が append される。"""
        path = tmp_path / 'trace.jsonl'
        with JsonlTraceRecorder(path) as rec:
            rec.record(TraceEventKind.RUN_START, run_id='exp-01')
            rec.record(TraceEventKind.OBSERVATION, tick=3, player_id=1, prose='扉が軋む')
            rec.record(TraceEventKind.MEMO_ADD, tick=3, player_id=1, memo_id='m1')
        lines = path.read_text(encoding='utf-8').splitlines()
        assert len(lines) == 3
        first = json.loads(lines[0])
        assert first['kind'] == TraceEventKind.RUN_START
        assert first['payload'] == {'run_id': 'exp-01'}

    def test_load_trace_events_event(self, tmp_path: Path) -> None:
        """JSONL 読み込みジェネレータが seq 順で TraceEvent を返す。"""
        path = tmp_path / 'trace.jsonl'
        with JsonlTraceRecorder(path) as rec:
            rec.record(TraceEventKind.ACTION, tick=1, player_id=1, tool='press')
            rec.record(TraceEventKind.ACTION_RESULT, tick=1, player_id=1, success=True)
        events = list(load_trace_events(path))
        assert [e.seq for e in events] == [1, 2]
        assert events[0].kind == TraceEventKind.ACTION
        assert events[1].payload == {'success': True}

    def test_advances_close_after_record_silently_drop(self, tmp_path: Path) -> None:
        """close 済み recorder への record は静かに drop し、件数を観測可能にする。

        Issue #311/#325 後続: 非同期 LLM 主観文付与 (#310) の worker thread が
        ``runtime.shutdown(timeout)`` のタイムアウト後に完了することがあり、
        その worker は閉じた recorder に書きに来る。これは構造的に避けがたい
        "close race" なので RuntimeError ではなく **silently drop +
        ``record_dropped_after_close`` カウンタ加算**で扱う。
        """
        path = tmp_path / 'trace.jsonl'
        rec = JsonlTraceRecorder(path)
        rec.close()
        ev = rec.record(TraceEventKind.NOTE, tick=42, message='post-close')
        assert ev.seq == -1
        assert ev.kind == 'note'
        assert ev.tick == 42
        assert rec.record_dropped_after_close == 1
        rec.record(TraceEventKind.NOTE)
        rec.record(TraceEventKind.NOTE)
        assert rec.record_dropped_after_close == 3
        content = path.read_text(encoding='utf-8')
        assert 'post-close' not in content

    def test_path_raises_type_error(self) -> None:
        """path に str が来たら TypeError。"""
        with pytest.raises(TypeError):
            JsonlTraceRecorder('/tmp/trace.jsonl')

    def test_seq_one_increases(self, tmp_path: Path) -> None:
        """recorder の seq は 1 から始まり各 record で 1 増える。"""
        path = tmp_path / 'trace.jsonl'
        with JsonlTraceRecorder(path) as rec:
            e1 = rec.record(TraceEventKind.TICK_START, tick=0)
            e2 = rec.record(TraceEventKind.TICK_END, tick=0)
        assert (e1.seq, e2.seq) == (1, 2)

class TestJsonlTraceRecorderCloseRaceWithWorkerThread:
    """閉じた recorder への書き込み (close race) の扱いを保証する。

    別の thread が、recorder を閉じたあとに record を呼ぶことがある。このときは
    例外を投げず、書き込みを捨てて ``record_dropped_after_close`` を進める。
    """

    def test_record_from_a_thread_after_close_increments_dropped_without_exception(self, tmp_path: Path) -> None:
        """recorder を閉じたあとに別 thread が record しても、例外を投げず dropped カウンタが進む。"""
        import threading

        recorder = JsonlTraceRecorder(tmp_path / 'trace.jsonl')
        closed = threading.Event()
        errors: list[BaseException] = []

        def _late_writer() -> None:
            closed.wait()
            try:
                recorder.record(TraceEventKind.TICK_END, tick=1)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        worker = threading.Thread(target=_late_writer)
        worker.start()
        recorder.close()
        closed.set()
        worker.join(timeout=5)

        assert errors == []
        assert recorder.record_dropped_after_close == 1
