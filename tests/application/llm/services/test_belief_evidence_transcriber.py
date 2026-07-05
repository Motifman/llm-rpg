"""BeliefEvidenceTranscriber の転記条件・trace 出力を保証する。

U2 (証拠台帳統一設計 §2 U2): 転記条件は「prediction_error が非 None」だけ。
それ以外の判定 (文字列一致カウンタ等) は作らない。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
    BeliefEvidenceTranscriber,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode


def _episode(**overrides) -> SubjectiveEpisode:
    base = dict(
        episode_id="ep-1",
        player_id=1,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(spot_id=3),
        action=EpisodeAction(tool_name="explore"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected="何か見つかるはず",
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
    )
    base.update(overrides)
    return SubjectiveEpisode(**base)


def _capture_trace(recorder: NullTraceRecorder) -> list:
    """NullTraceRecorder.record を wrap して返り値の TraceEvent を capture する。

    ``test_episodic_trace_emission.py`` と同じ規約 (専用の in-memory
    recorder クラスは作らず、NullTraceRecorder の戻り値を横取りする)。
    """
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


class TestBeliefEvidenceTranscriberRecordCondition:
    def test_prediction_error_none_does_not_record(self) -> None:
        """転記条件: prediction_error が None なら evidence を積まない。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(being_id, _episode(prediction_error=None))

        assert result is None
        assert buffer_store.list_all_by_being(being_id) == []

    def test_prediction_error_non_none_records_one_evidence(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id, _episode(prediction_error="何もなかった")
        )

        assert result is not None
        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].text == "何もなかった"
        assert rows[0].episode_ids == ("ep-1",)
        assert rows[0].cue_signature == "tool:explore|spot:3"

    def test_records_are_scoped_per_being(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_a = BeingId("being-a")
        being_b = BeingId("being-b")

        transcriber.record_if_applicable(
            being_a, _episode(prediction_error="外れた")
        )

        assert len(buffer_store.list_all_by_being(being_a)) == 1
        assert buffer_store.list_all_by_being(being_b) == []


class TestBeliefEvidenceTranscriberTick:
    def test_tick_comes_from_current_tick_provider(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, current_tick_provider=lambda: 42
        )
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="外れた")
        )

        assert buffer_store.list_all_by_being(being_id)[0].tick == 42

    def test_tick_provider_exception_falls_back_to_none(self) -> None:
        """current_tick_provider が例外を投げても転記本体は止めない。"""

        def _raising() -> int:
            raise RuntimeError("boom")

        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, current_tick_provider=_raising
        )
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id, _episode(prediction_error="外れた")
        )

        assert result is not None
        assert buffer_store.list_all_by_being(being_id)[0].tick is None


class TestBeliefEvidenceTranscriberTrace:
    def test_emits_belief_evidence_trace_event(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = BeliefEvidenceTranscriber(
            buffer_store,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 5,
        )
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="想定外だった")
        )

        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE]
        assert len(events) == 1
        payload = events[0].payload
        assert payload["being_id"] == "being-1"
        assert payload["source_kind"] == "prediction_error"
        assert payload["cue_signature"] == "tool:explore|spot:3"
        assert payload["episode_ids"] == ["ep-1"]
        assert events[0].tick == 5

    def test_no_trace_recorder_provider_is_safe(self) -> None:
        """trace_recorder_provider 未注入でも転記自体は成功する。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id, _episode(prediction_error="想定外だった")
        )

        assert result is not None

    def test_no_evidence_means_no_trace(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, trace_recorder_provider=lambda: recorder
        )
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(being_id, _episode(prediction_error=None))

        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE]
        assert events == []


class TestBeliefEvidenceTranscriberTypeGuards:
    def test_rejects_non_being_id(self) -> None:
        transcriber = BeliefEvidenceTranscriber(InMemoryBeliefEvidenceBufferStore())
        with pytest.raises(TypeError):
            transcriber.record_if_applicable("being-1", _episode())

    def test_rejects_non_episode(self) -> None:
        transcriber = BeliefEvidenceTranscriber(InMemoryBeliefEvidenceBufferStore())
        with pytest.raises(TypeError):
            transcriber.record_if_applicable(BeingId("being-1"), "not-an-episode")

    def test_rejects_non_repository_buffer_store(self) -> None:
        with pytest.raises(TypeError):
            BeliefEvidenceTranscriber(object())
