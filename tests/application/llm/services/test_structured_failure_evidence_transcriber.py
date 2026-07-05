"""StructuredFailureEvidenceTranscriber の転記条件・anchor 選択・trace 出力を保証する。

U6 (予測誤差統一設計 §2 U6 / semantic_learning_consolidation_design.md
「証拠の入口」表の STRUCTURED_FAILURE 行): loop_guard の cross_tick_failure
閾値到達を、その being の直近 episode に anchor して BeliefEvidence に転記する。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.structured_failure_evidence_transcriber import (
    StructuredFailureEvidenceTranscriber,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)


def _episode(episode_id: str, *, occurred_at: datetime) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=1,
        occurred_at=occurred_at,
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(),
        action=EpisodeAction(tool_name="spot_graph_interact"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
    )


def _capture_trace(recorder: NullTraceRecorder) -> list:
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


class TestStructuredFailureEvidenceTranscriberAnchor:
    def test_no_episode_returns_none_and_skips(self) -> None:
        """anchor する episode が無ければ evidence を作らず None を返す
        (捏造しない。warning ログで可視化)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        transcriber = StructuredFailureEvidenceTranscriber(buffer_store, episode_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_triggered(
            being_id,
            tool_name="spot_graph_interact",
            error_code="INTERACTION_PRECONDITION_FAILED",
            count=3,
        )

        assert result is None
        assert buffer_store.list_all_by_being(being_id) == []

    def test_anchors_to_latest_episode(self) -> None:
        """複数 episode があるとき、最新 (occurred_at 最大) の episode に
        anchor する。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        transcriber = StructuredFailureEvidenceTranscriber(buffer_store, episode_store)
        being_id = BeingId("being-1")
        episode_store.put_by_being(
            being_id, _episode("ep-old", occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
        )
        episode_store.put_by_being(
            being_id, _episode("ep-new", occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc))
        )

        result = transcriber.record_if_triggered(
            being_id,
            tool_name="spot_graph_interact",
            error_code="INTERACTION_PRECONDITION_FAILED",
            count=3,
        )

        assert result is not None
        assert result.episode_ids == ("ep-new",)


class TestStructuredFailureEvidenceTranscriberContent:
    def _setup(self):
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        being_id = BeingId("being-1")
        episode_store.put_by_being(
            being_id, _episode("ep-1", occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
        )
        return buffer_store, episode_store, being_id

    def test_source_kind_is_structured_failure(self) -> None:
        buffer_store, episode_store, being_id = self._setup()
        transcriber = StructuredFailureEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_if_triggered(
            being_id,
            tool_name="spot_graph_interact",
            error_code="INTERACTION_PRECONDITION_FAILED",
            count=3,
        )

        evidence = buffer_store.list_all_by_being(being_id)[0]
        assert evidence.source_kind == BeliefEvidenceSourceKind.STRUCTURED_FAILURE

    def test_cue_signature_is_tool_axis_only(self) -> None:
        """design 通り cue_signature は "tool:<tool_name>" 固定 (U3b の
        shortlist と一致させるため spot/player は付けない)。"""
        buffer_store, episode_store, being_id = self._setup()
        transcriber = StructuredFailureEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_if_triggered(
            being_id,
            tool_name="spot_graph_interact",
            error_code="INTERACTION_PRECONDITION_FAILED",
            count=3,
        )

        evidence = buffer_store.list_all_by_being(being_id)[0]
        assert evidence.cue_signature == "tool:spot_graph_interact"

    def test_salience_is_low(self) -> None:
        """件数駆動の早期 trigger は cue_signature 反復側に任せるため、
        STRUCTURED_FAILURE evidence 自体の salience は常に low。"""
        buffer_store, episode_store, being_id = self._setup()
        transcriber = StructuredFailureEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_if_triggered(
            being_id,
            tool_name="spot_graph_interact",
            error_code="INTERACTION_PRECONDITION_FAILED",
            count=3,
        )

        assert buffer_store.list_all_by_being(being_id)[0].salience == "low"

    def test_text_mentions_tool_and_error_code_and_count(self) -> None:
        buffer_store, episode_store, being_id = self._setup()
        transcriber = StructuredFailureEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_if_triggered(
            being_id,
            tool_name="spot_graph_interact",
            error_code="INTERACTION_PRECONDITION_FAILED",
            count=3,
        )

        text = buffer_store.list_all_by_being(being_id)[0].text
        assert "spot_graph_interact" in text
        assert "INTERACTION_PRECONDITION_FAILED" in text
        assert "3" in text


class TestStructuredFailureEvidenceTranscriberTrace:
    def test_emits_belief_evidence_trace_event(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        being_id = BeingId("being-1")
        episode_store.put_by_being(
            being_id, _episode("ep-1", occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
        )
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = StructuredFailureEvidenceTranscriber(
            buffer_store,
            episode_store,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 7,
        )

        transcriber.record_if_triggered(
            being_id,
            tool_name="spot_graph_interact",
            error_code="INTERACTION_PRECONDITION_FAILED",
            count=3,
        )

        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE]
        assert len(events) == 1
        payload = events[0].payload
        assert payload["source_kind"] == "structured_failure"
        assert payload["being_id"] == "being-1"
        assert events[0].tick == 7


class TestStructuredFailureEvidenceTranscriberTypeGuards:
    def test_rejects_non_repository_episode_store(self) -> None:
        with pytest.raises(TypeError):
            StructuredFailureEvidenceTranscriber(
                InMemoryBeliefEvidenceBufferStore(), object()
            )

    def test_rejects_non_being_id(self) -> None:
        transcriber = StructuredFailureEvidenceTranscriber(
            InMemoryBeliefEvidenceBufferStore(), InMemorySubjectiveEpisodeStore()
        )
        with pytest.raises(TypeError):
            transcriber.record_if_triggered(
                "being-1", tool_name="t", error_code="E", count=1
            )
