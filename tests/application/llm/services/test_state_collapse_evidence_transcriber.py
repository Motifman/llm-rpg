"""StateCollapseEvidenceTranscriber の転記条件・dedup・trace 出力を保証する。

PR-D (状態破綻を高 salience evidence として記憶化): 「is_down への遷移」
「hunger max 到達」という、エンジン側で既に確定した事実を BeliefEvidence に
転記する。判定はエンジン側の状態遷移そのものであり、本クラスは新しい判定
基準を追加しない (structured_failure_evidence_transcriber と同じ「転記のみ」
方針)。text は事実の記述に留め、教訓や指示は含めない。
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
from ai_rpg_world.application.llm.services.state_collapse_evidence_transcriber import (
    StateCollapseEvidenceTranscriber,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_HIGH,
)
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


def _setup():
    buffer_store = InMemoryBeliefEvidenceBufferStore()
    episode_store = InMemorySubjectiveEpisodeStore()
    being_id = BeingId("being-1")
    episode_store.put_by_being(
        being_id, _episode("ep-1", occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    )
    return buffer_store, episode_store, being_id


class TestStateCollapseEvidenceTranscriberAnchor:
    def test_no_episode_returns_none_and_skips(self) -> None:
        """anchor する episode が無ければ evidence を作らず None を返す
        (捏造しない。warning ログで可視化)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        transcriber = StateCollapseEvidenceTranscriber(buffer_store, episode_store)
        being_id = BeingId("being-1")

        result = transcriber.record_down_evidence(being_id)

        assert result is None
        assert buffer_store.list_all_by_being(being_id) == []


class TestStateCollapseEvidenceTranscriberDownTransition:
    def test_down_evidence_is_high_salience_state_collapse(self) -> None:
        buffer_store, episode_store, being_id = _setup()
        transcriber = StateCollapseEvidenceTranscriber(buffer_store, episode_store)

        result = transcriber.record_down_evidence(being_id)

        assert result is not None
        evidence = buffer_store.list_all_by_being(being_id)[0]
        assert evidence.salience == BELIEF_EVIDENCE_SALIENCE_HIGH
        assert evidence.source_kind == BeliefEvidenceSourceKind.STATE_COLLAPSE
        assert evidence.cue_signature == "state:down"

    def test_text_states_fact_without_lesson_or_instruction(self) -> None:
        """text は「戦闘不能になった」という事実の記述のみ。教訓・指示語を含めない。"""
        buffer_store, episode_store, being_id = _setup()
        transcriber = StateCollapseEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_down_evidence(being_id)

        text = buffer_store.list_all_by_being(being_id)[0].text
        assert "戦闘不能" in text
        for banned in ("べき", "しよう", "注意", "危険"):
            assert banned not in text

    def test_second_call_while_still_down_is_skipped(self) -> None:
        """down 状態が続いている間 (clear_down_state を呼ぶまで) は
        record_down_evidence を再度呼んでも重複しない。"""
        buffer_store, episode_store, being_id = _setup()
        transcriber = StateCollapseEvidenceTranscriber(buffer_store, episode_store)

        first = transcriber.record_down_evidence(being_id)
        second = transcriber.record_down_evidence(being_id)

        assert first is not None
        assert second is None
        assert len(buffer_store.list_all_by_being(being_id)) == 1

    def test_after_clear_down_state_a_new_down_records_new_evidence(self) -> None:
        """復帰 (clear_down_state) 後に再度 down したら新しい evidence が積まれる。"""
        buffer_store, episode_store, being_id = _setup()
        transcriber = StateCollapseEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_down_evidence(being_id)
        transcriber.clear_down_state(being_id)
        second = transcriber.record_down_evidence(being_id)

        assert second is not None
        assert len(buffer_store.list_all_by_being(being_id)) == 2

    def test_clear_down_state_without_prior_record_is_noop(self) -> None:
        """record 前に clear を呼んでも例外にならない (冪等)。"""
        buffer_store, episode_store, being_id = _setup()
        transcriber = StateCollapseEvidenceTranscriber(buffer_store, episode_store)

        transcriber.clear_down_state(being_id)  # 例外にならないことを確認


class TestStateCollapseEvidenceTranscriberHungerMaxTransition:
    def test_hunger_max_evidence_is_high_salience_state_collapse(self) -> None:
        buffer_store, episode_store, being_id = _setup()
        transcriber = StateCollapseEvidenceTranscriber(buffer_store, episode_store)

        result = transcriber.record_hunger_max_evidence(being_id)

        assert result is not None
        evidence = buffer_store.list_all_by_being(being_id)[0]
        assert evidence.salience == BELIEF_EVIDENCE_SALIENCE_HIGH
        assert evidence.source_kind == BeliefEvidenceSourceKind.STATE_COLLAPSE
        assert evidence.cue_signature == "state:hunger_max"
        assert "空腹" in evidence.text

    def test_second_call_while_still_at_max_is_skipped(self) -> None:
        buffer_store, episode_store, being_id = _setup()
        transcriber = StateCollapseEvidenceTranscriber(buffer_store, episode_store)

        first = transcriber.record_hunger_max_evidence(being_id)
        second = transcriber.record_hunger_max_evidence(being_id)

        assert first is not None
        assert second is None
        assert len(buffer_store.list_all_by_being(being_id)) == 1

    def test_after_clear_hunger_max_state_a_new_max_records_new_evidence(self) -> None:
        buffer_store, episode_store, being_id = _setup()
        transcriber = StateCollapseEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_hunger_max_evidence(being_id)
        transcriber.clear_hunger_max_state(being_id)
        second = transcriber.record_hunger_max_evidence(being_id)

        assert second is not None
        assert len(buffer_store.list_all_by_being(being_id)) == 2


class TestStateCollapseEvidenceTranscriberIndependentDedupTracking:
    def test_down_and_hunger_max_dedup_state_are_independent_per_being(self) -> None:
        """down の dedup 状態と hunger max の dedup 状態は独立している
        (片方を clear してももう片方は影響を受けない)。"""
        buffer_store, episode_store, being_id = _setup()
        transcriber = StateCollapseEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_down_evidence(being_id)
        transcriber.record_hunger_max_evidence(being_id)
        transcriber.clear_down_state(being_id)
        again_down = transcriber.record_down_evidence(being_id)
        again_hunger = transcriber.record_hunger_max_evidence(being_id)

        assert again_down is not None
        assert again_hunger is None

    def test_dedup_state_is_tracked_per_being_id(self) -> None:
        """being ごとに dedup 状態を持つ (他 being の down が影響しない)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        being_a = BeingId("being-a")
        being_b = BeingId("being-b")
        for bid in (being_a, being_b):
            episode_store.put_by_being(
                bid, _episode(f"ep-{bid.value}", occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
            )
        transcriber = StateCollapseEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_down_evidence(being_a)
        result_b = transcriber.record_down_evidence(being_b)

        assert result_b is not None


class TestStateCollapseEvidenceTranscriberTrace:
    def test_emits_belief_evidence_trace_event_for_down(self) -> None:
        buffer_store, episode_store, being_id = _setup()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = StateCollapseEvidenceTranscriber(
            buffer_store,
            episode_store,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 7,
        )

        transcriber.record_down_evidence(being_id)

        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE]
        assert len(events) == 1
        payload = events[0].payload
        assert payload["source_kind"] == "state_collapse"
        assert payload["being_id"] == "being-1"
        assert events[0].tick == 7

    def test_emits_belief_evidence_trace_event_for_hunger_max(self) -> None:
        buffer_store, episode_store, being_id = _setup()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = StateCollapseEvidenceTranscriber(
            buffer_store,
            episode_store,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 9,
        )

        transcriber.record_hunger_max_evidence(being_id)

        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE]
        assert len(events) == 1
        assert events[0].tick == 9


class TestStateCollapseEvidenceTranscriberTypeGuards:
    def test_rejects_non_repository_episode_store(self) -> None:
        with pytest.raises(TypeError):
            StateCollapseEvidenceTranscriber(
                InMemoryBeliefEvidenceBufferStore(), object()
            )

    def test_rejects_non_being_id_for_down(self) -> None:
        transcriber = StateCollapseEvidenceTranscriber(
            InMemoryBeliefEvidenceBufferStore(), InMemorySubjectiveEpisodeStore()
        )
        with pytest.raises(TypeError):
            transcriber.record_down_evidence("being-1")

    def test_rejects_non_being_id_for_hunger_max(self) -> None:
        transcriber = StateCollapseEvidenceTranscriber(
            InMemoryBeliefEvidenceBufferStore(), InMemorySubjectiveEpisodeStore()
        )
        with pytest.raises(TypeError):
            transcriber.record_hunger_max_evidence("being-1")
