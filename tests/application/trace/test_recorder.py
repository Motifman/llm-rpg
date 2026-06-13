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

    def test_close_後の_record_は_silently_drop_されカウンタが進む(
        self, tmp_path: Path
    ) -> None:
        """close 済み recorder への record は静かに drop し、件数を観測可能にする。

        Issue #311/#325 後続: 非同期 LLM 主観文付与 (#310) の worker thread が
        ``runtime.shutdown(timeout)`` のタイムアウト後に完了することがあり、
        その worker は閉じた recorder に書きに来る。これは構造的に避けがたい
        "close race" なので RuntimeError ではなく **silently drop +
        ``record_dropped_after_close`` カウンタ加算**で扱う。
        """
        path = tmp_path / "trace.jsonl"
        rec = JsonlTraceRecorder(path)
        rec.close()
        # 例外は投げない (= async worker から呼ばれても WARN ノイズを出さない)
        ev = rec.record(TraceEventKind.NOTE, tick=42, message="post-close")
        # caller チェーン継続のため sentinel TraceEvent (seq=-1) を返す
        assert ev.seq == -1
        assert ev.kind == "note"
        assert ev.tick == 42
        assert rec.record_dropped_after_close == 1
        # 複数回呼ばれてもカウンタが正しく進む
        rec.record(TraceEventKind.NOTE)
        rec.record(TraceEventKind.NOTE)
        assert rec.record_dropped_after_close == 3
        # ファイルには post-close 書き込みが入っていないこと
        content = path.read_text(encoding="utf-8")
        assert "post-close" not in content

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


class TestJsonlTraceRecorderCloseRaceWithAsyncScheduler:
    """非同期 LLM 主観文付与 scheduler との close race (#311/#325 後続)。

    実シナリオでは ``ThreadPoolEpisodicSubjectiveScheduler`` の worker thread が
    ``runtime.shutdown(timeout)`` のタイムアウト後に完了し、閉じた recorder
    に書きに来るケースがある。本テストは:

    1. recorder を with 文で開く
    2. ``trace_recorder_provider`` で recorder を持つ scheduler を作る
    3. delay 付きの stub LLM port で worker を仕込む
    4. shutdown を timeout=0 で諦める (= worker は走り続ける)
    5. with 文を抜けて recorder を閉じる
    6. worker が完了して record を呼ぶ → drop counter が進む / 例外なし

    という流れを再現する。
    """

    def test_async_worker_が_close_後に_record_しても_例外なく_dropped_カウンタが進む(
        self, tmp_path: Path
    ) -> None:
        import time
        from datetime import datetime, timezone
        from typing import Any

        from ai_rpg_world.application.llm.contracts.chunk_encoding import (
            build_chunk_encoding_input,
        )
        from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
        from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
            IEpisodicChunkSubjectiveCompletionPort,
        )
        from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
            ChunkEpisodeDraftBuilder,
        )
        from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
            EpisodicChunkSubjectiveFieldsService,
        )
        from ai_rpg_world.application.llm.services.episodic_subjective_completion_schedulers import (
            ThreadPoolEpisodicSubjectiveScheduler,
        )
        from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
            InMemorySubjectiveEpisodeStore,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        class _SlowPort(IEpisodicChunkSubjectiveCompletionPort):
            def complete_episode_subjective_json(
                self, messages: list[dict[str, Any]]
            ) -> dict[str, Any]:
                time.sleep(0.3)  # close 後完了を意図的に作る
                return {"interpreted": "x", "recall_text": "y"}

        store = InMemorySubjectiveEpisodeStore()
        path = tmp_path / "trace.jsonl"
        recorder = JsonlTraceRecorder(path)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(_SlowPort()),
            store,
            trace_recorder_provider=lambda: recorder,
        )
        # draft 1 件作って submit
        act = ActionResultEntry(
            occurred_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            action_summary="待機",
            result_summary="ok",
            tool_name="spot_graph_wait",
        )
        enc = build_chunk_encoding_input(PlayerId(1), (), (act,))
        draft = ChunkEpisodeDraftBuilder().build(enc)
        store.put(draft)
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        # 即座に shutdown timeout=0 → worker は drop されず走り続ける
        scheduler.shutdown(timeout=0.01)
        # recorder を閉じる
        recorder.close()
        # worker の完了待ち (delay 0.3s より長く待つ)
        time.sleep(0.5)
        # close 後に record が来ても例外は出ない、counter は進んでいる
        assert recorder.record_dropped_after_close >= 1
