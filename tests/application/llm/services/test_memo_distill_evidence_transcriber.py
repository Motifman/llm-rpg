"""MemoDistillEvidenceTranscriber の転記条件・anchor 選択・trace 出力を保証する。

U5 (予測誤差統一設計 §2 U5 / semantic_learning_consolidation_design.md
「証拠の入口」表の MEMO_DISTILL 行): memo_done で完了した memo 本文を、
その being の直近 episode に anchor して無条件で BeliefEvidence に転記する。
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
from ai_rpg_world.application.llm.services.memo_distill_evidence_transcriber import (
    MEMO_DISTILL_CUE_SIGNATURE,
    MemoDistillEvidenceTranscriber,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import (
    MemoFulfillmentContext,
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
        action=EpisodeAction(tool_name="memo_done"),
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


class TestMemoDistillEvidenceTranscriberAnchor:
    def test_no_episode_returns_none_and_skips(self) -> None:
        """anchor する episode が無ければ evidence を作らず None を返す
        (捏造しない。warning ログで可視化)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        transcriber = MemoDistillEvidenceTranscriber(buffer_store, episode_store)
        being_id = BeingId("being-1")

        result = transcriber.record_from_memo(
            being_id, memo_content="岩礁海岸は山方面に通じず×", fulfillment_context=None
        )

        assert result is None
        assert buffer_store.list_all_by_being(being_id) == []

    def test_anchors_to_latest_episode(self) -> None:
        """複数 episode があるとき、最新 (occurred_at 最大) の episode に
        anchor する。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        transcriber = MemoDistillEvidenceTranscriber(buffer_store, episode_store)
        being_id = BeingId("being-1")
        episode_store.put_by_being(
            being_id, _episode("ep-old", occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
        )
        episode_store.put_by_being(
            being_id, _episode("ep-new", occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc))
        )

        result = transcriber.record_from_memo(
            being_id, memo_content="拠点に資源はない", fulfillment_context=None
        )

        assert result is not None
        assert result.episode_ids == ("ep-new",)


class TestMemoDistillEvidenceTranscriberContent:
    def _setup(self):
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        being_id = BeingId("being-1")
        episode_store.put_by_being(
            being_id, _episode("ep-1", occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
        )
        return buffer_store, episode_store, being_id

    def test_source_kind_is_memo_distill(self) -> None:
        buffer_store, episode_store, being_id = self._setup()
        transcriber = MemoDistillEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_from_memo(
            being_id, memo_content="岩礁海岸は山方面に通じず×", fulfillment_context=None
        )

        evidence = buffer_store.list_all_by_being(being_id)[0]
        assert evidence.source_kind == BeliefEvidenceSourceKind.MEMO_DISTILL

    def test_cue_signature_is_fixed_self_memo(self) -> None:
        """memo は tool/spot のような固定 cue を持たないため、
        cue_signature は "self:memo" 固定。"""
        buffer_store, episode_store, being_id = self._setup()
        transcriber = MemoDistillEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_from_memo(
            being_id, memo_content="岩礁海岸は山方面に通じず×", fulfillment_context=None
        )

        evidence = buffer_store.list_all_by_being(being_id)[0]
        assert evidence.cue_signature == "self:memo"
        assert evidence.cue_signature == MEMO_DISTILL_CUE_SIGNATURE

    def test_salience_is_low(self) -> None:
        buffer_store, episode_store, being_id = self._setup()
        transcriber = MemoDistillEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_from_memo(
            being_id, memo_content="岩礁海岸は山方面に通じず×", fulfillment_context=None
        )

        assert buffer_store.list_all_by_being(being_id)[0].salience == "low"

    def test_text_contains_memo_content(self) -> None:
        buffer_store, episode_store, being_id = self._setup()
        transcriber = MemoDistillEvidenceTranscriber(buffer_store, episode_store)

        transcriber.record_from_memo(
            being_id, memo_content="岩礁海岸は山方面に通じず×", fulfillment_context=None
        )

        text = buffer_store.list_all_by_being(being_id)[0].text
        assert "岩礁海岸は山方面に通じず×" in text

    def test_text_includes_fulfillment_context(self) -> None:
        """fulfillment_context が渡されたら観測 / 行動の抜粋も text に含める。"""
        buffer_store, episode_store, being_id = self._setup()
        transcriber = MemoDistillEvidenceTranscriber(buffer_store, episode_store)
        context = MemoFulfillmentContext(
            completed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            completed_at_tick=5,
            recent_observation_proses=("山道は行き止まりだった",),
            recent_action_summaries=("山方面へ移動を試みた",),
        )

        transcriber.record_from_memo(
            being_id, memo_content="岩礁海岸は山方面に通じず×", fulfillment_context=context
        )

        text = buffer_store.list_all_by_being(being_id)[0].text
        assert "岩礁海岸は山方面に通じず×" in text
        assert "山道は行き止まりだった" in text
        assert "山方面へ移動を試みた" in text

    def test_transcribes_unconditionally_even_if_memo_looks_noisy(self) -> None:
        """ノイズ (一般化不能なタスクメモ) かどうかはここで判定しない。
        discard 判定は固着パスの LLM に委ねるため、本転記器は常に積む。"""
        buffer_store, episode_store, being_id = self._setup()
        transcriber = MemoDistillEvidenceTranscriber(buffer_store, episode_store)

        result = transcriber.record_from_memo(
            being_id, memo_content="扉固定スイッチを押す", fulfillment_context=None
        )

        assert result is not None
        assert len(buffer_store.list_all_by_being(being_id)) == 1


class TestMemoDistillEvidenceTranscriberTrace:
    def test_emits_belief_evidence_trace_event(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        being_id = BeingId("being-1")
        episode_store.put_by_being(
            being_id, _episode("ep-1", occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
        )
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = MemoDistillEvidenceTranscriber(
            buffer_store,
            episode_store,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 7,
        )

        transcriber.record_from_memo(
            being_id, memo_content="岩礁海岸は山方面に通じず×", fulfillment_context=None
        )

        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE]
        assert len(events) == 1
        payload = events[0].payload
        assert payload["source_kind"] == "memo_distill"
        assert payload["being_id"] == "being-1"
        assert events[0].tick == 7


class TestMemoDistillEvidenceTranscriberTypeGuards:
    def test_rejects_non_repository_episode_store(self) -> None:
        with pytest.raises(TypeError):
            MemoDistillEvidenceTranscriber(
                InMemoryBeliefEvidenceBufferStore(), object()
            )

    def test_rejects_non_being_id(self) -> None:
        transcriber = MemoDistillEvidenceTranscriber(
            InMemoryBeliefEvidenceBufferStore(), InMemorySubjectiveEpisodeStore()
        )
        with pytest.raises(TypeError):
            transcriber.record_from_memo(
                "being-1", memo_content="x", fulfillment_context=None
            )

    def test_rejects_empty_memo_content(self) -> None:
        transcriber = MemoDistillEvidenceTranscriber(
            InMemoryBeliefEvidenceBufferStore(), InMemorySubjectiveEpisodeStore()
        )
        with pytest.raises(TypeError):
            transcriber.record_from_memo(
                BeingId("being-1"), memo_content="   ", fulfillment_context=None
            )
