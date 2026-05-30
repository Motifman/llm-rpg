"""ObservationAppender のテスト（正常・境界・例外）"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.contracts.interfaces import IObservationContextBuffer
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestObservationAppenderNormal:
    """append の正常ケース"""

    @pytest.fixture
    def buffer(self):
        return DefaultObservationContextBuffer()

    @pytest.fixture
    def appender(self, buffer):
        return ObservationAppender(buffer=buffer)

    def test_append_adds_entry_to_buffer_with_all_fields(
        self, appender, buffer
    ):
        """全フィールド指定時に観測がバッファに追加される"""
        player_id = PlayerId(1)
        output = ObservationOutput(
            prose="テスト観測",
            structured={"type": "test"},
        )
        occurred_at = datetime(2025, 3, 14, 12, 0, 0)
        game_time_label = "1年1月1日 00:00:00"

        appender.append(
            player_id=player_id,
            output=output,
            occurred_at=occurred_at,
            game_time_label=game_time_label,
        )

        entries = buffer.get_observations(player_id)
        assert len(entries) == 1
        assert entries[0].occurred_at == occurred_at
        assert entries[0].output == output
        assert entries[0].game_time_label == game_time_label

    def test_append_with_game_time_label_none(self, appender, buffer):
        """game_time_label が None でも正常に追加される"""
        player_id = PlayerId(2)
        output = ObservationOutput(
            prose="時刻なし観測",
            structured={},
        )
        occurred_at = datetime.now()

        appender.append(
            player_id=player_id,
            output=output,
            occurred_at=occurred_at,
            game_time_label=None,
        )

        entries = buffer.get_observations(player_id)
        assert len(entries) == 1
        assert entries[0].game_time_label is None

    def test_append_multiple_entries_for_same_player(self, appender, buffer):
        """同一プレイヤーに複数追加すると順序保持される"""
        player_id = PlayerId(1)
        for i in range(3):
            output = ObservationOutput(
                prose=f"観測{i}",
                structured={"index": i},
            )
            occurred_at = datetime(2025, 3, 14, 12, i, 0)
            appender.append(
                player_id=player_id,
                output=output,
                occurred_at=occurred_at,
                game_time_label=None,
            )

        entries = buffer.get_observations(player_id)
        assert len(entries) == 3
        assert [e.output.structured["index"] for e in entries] == [0, 1, 2]

    def test_runtime_context_provider_passed_to_buffer(self) -> None:
        """runtime_context_provider が戻した値が buffer.append に渡る"""
        calls = []

        def provider(pid: PlayerId) -> ToolRuntimeContextDto:
            assert pid.value == 1
            return ToolRuntimeContextDto(targets={}, current_spot_id=12)

        class CaptureBuffer(IObservationContextBuffer):
            def append(self, player_id, entry, *, runtime_context=None):
                calls.append((player_id, entry, runtime_context))

            def get_observations(self, player_id):
                return []

            def drain(self, player_id):
                return []

        cap = CaptureBuffer()
        appender = ObservationAppender(
            buffer=cap, runtime_context_provider=provider
        )
        out = ObservationOutput(prose="x", structured={"type": "t"})
        appender.append(PlayerId(1), out, datetime.now(), None)
        assert len(calls) == 1
        assert calls[0][2] is not None and calls[0][2].current_spot_id == 12


class TestObservationAppenderExceptions:
    """例外伝播のテスト"""

    def test_append_propagates_buffer_exception(self):
        """buffer.append が例外を投げた場合、その例外を伝播する"""
        buffer = MagicMock(spec=IObservationContextBuffer)
        buffer.append.side_effect = RuntimeError("buffer write failed")
        appender = ObservationAppender(buffer=buffer)

        with pytest.raises(RuntimeError, match="buffer write failed"):
            appender.append(
                player_id=PlayerId(1),
                output=ObservationOutput(prose="test", structured={}),
                occurred_at=datetime.now(),
                game_time_label=None,
            )

    def test_append_propagates_invalid_output_exception(self):
        """無効な output で ObservationEntry 構築に失敗した場合、例外を伝播する"""
        buffer = DefaultObservationContextBuffer()
        appender = ObservationAppender(buffer=buffer)

        with pytest.raises(TypeError):
            appender.append(
                player_id=PlayerId(1),
                output=None,  # ObservationOutput でない
                occurred_at=datetime.now(),
                game_time_label=None,
            )


class TestObservationAppenderTraceRecording:
    """Issue #276: trace_recorder 注入時、buffer append と同じ場所で
    ``TraceEventKind.OBSERVATION`` を記録する。"""

    def _make_output(self, prose: str = "リンの声がかすかに聞こえる") -> ObservationOutput:
        return ObservationOutput(
            prose=prose,
            structured={"sound_clarity": "FAINT", "speaker": "リン"},
            observation_category="social",
            schedules_turn=True,
        )

    def test_trace_recorder_注入時_observation_イベントが記録される(self):
        """append 1 件で trace に kind=OBSERVATION が 1 件残る。"""
        from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind

        buffer = DefaultObservationContextBuffer()
        recorder = NullTraceRecorder()
        recorded = []
        original_record = recorder.record

        def capture(kind, **kw):
            ev = original_record(kind, **kw)
            recorded.append(ev)
            return ev

        recorder.record = capture  # type: ignore[method-assign]
        appender = ObservationAppender(
            buffer=buffer,
            trace_recorder=recorder,
            current_tick_provider=lambda: 42,
        )

        appender.append(
            player_id=PlayerId(7),
            output=self._make_output(),
            occurred_at=datetime.now(),
            game_time_label="深夜 0:25",
        )

        assert len(recorded) == 1
        ev = recorded[0]
        assert ev.kind == TraceEventKind.OBSERVATION
        assert ev.tick == 42
        assert ev.player_id == 7
        assert "かすかに聞こえる" in ev.payload["prose"]
        assert ev.payload["structured"]["sound_clarity"] == "FAINT"
        assert ev.payload["observation_category"] == "social"
        assert ev.payload["schedules_turn"] is True
        assert ev.payload["game_time_label"] == "深夜 0:25"

    def test_trace_recorder_未注入なら_record_しない(self):
        """trace_recorder=None なら buffer は更新するが trace 呼び出しなし。"""
        buffer = DefaultObservationContextBuffer()
        appender = ObservationAppender(buffer=buffer)
        appender.append(
            player_id=PlayerId(1),
            output=self._make_output(),
            occurred_at=datetime.now(),
            game_time_label=None,
        )
        assert len(buffer.get_observations(PlayerId(1))) == 1

    def test_provider_経由で_遅延注入された_recorder_に追従する(self):
        """trace_recorder_provider 経路: 後から差し替えられた recorder を毎回 lookup する。"""
        from ai_rpg_world.application.trace import NullTraceRecorder

        buffer = DefaultObservationContextBuffer()
        recorder_holder = {"r": None}
        appender = ObservationAppender(
            buffer=buffer,
            trace_recorder_provider=lambda: recorder_holder["r"],
        )

        # 1 回目: provider が None を返すので trace されない
        appender.append(
            player_id=PlayerId(1),
            output=self._make_output(),
            occurred_at=datetime.now(),
            game_time_label=None,
        )

        # provider に recorder を差し込み
        recorder = NullTraceRecorder()
        seen = []
        original = recorder.record
        recorder.record = lambda k, **kw: seen.append(original(k, **kw))  # type: ignore[method-assign]
        recorder_holder["r"] = recorder

        # 2 回目: 今度は trace される
        appender.append(
            player_id=PlayerId(1),
            output=self._make_output(),
            occurred_at=datetime.now(),
            game_time_label=None,
        )
        assert len(seen) == 1

    def test_trace_record_失敗は_buffer_append_を止めない(self):
        """recorder.record が例外を投げても buffer への append は完了する。"""
        from ai_rpg_world.application.trace import NullTraceRecorder

        buffer = DefaultObservationContextBuffer()
        recorder = NullTraceRecorder()
        recorder.record = MagicMock(side_effect=RuntimeError("trace io fail"))  # type: ignore[method-assign]
        appender = ObservationAppender(buffer=buffer, trace_recorder=recorder)
        appender.append(
            player_id=PlayerId(1),
            output=self._make_output(),
            occurred_at=datetime.now(),
            game_time_label=None,
        )
        # buffer には残っている
        assert len(buffer.get_observations(PlayerId(1))) == 1

