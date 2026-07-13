"""record_pending_prediction_if_applicable が容量あふれによる evict を trace に

残すことを保証する (LOW-1)。

容量上限 (既定 8 件) を超えて新しい約束を積むと、per-Being store が最も
古い未決着の約束を黙って evict する。この evict は導入時 trace が無く、run
分析で「作られたのに RESOLVED も EXPIRED も無い pending」が謎として残る
原因になっていた。store の ``add_by_being`` が evict した
``PendingPrediction`` を戻り値で返すよう変更し、記録経路がそれを使って
``PENDING_PREDICTION_EVICTED`` を 1 件残すことを確認する。
"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.llm.services._pending_prediction_recording import (
    record_pending_prediction_if_applicable,
)
from ai_rpg_world.application.llm.services.in_memory_pending_prediction_store import (
    InMemoryPendingPredictionStore,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPredictionDraft,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)

_BEING = BeingId("being-1")


def _episode_with_draft(episode_id: str, *, tick_offset_to: int = 6) -> SubjectiveEpisode:
    draft = PendingPredictionDraft(
        text="夕方に木の下でカイトと交換する",
        resolution_cues=("spot:12",),
        tick_offset_from=2,
        tick_offset_to=tick_offset_to,
    )
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=1,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(spot_id=12),
        action=EpisodeAction(tool_name="explore"),
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
        pending_prediction_draft=draft,
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


class TestPendingRecordingEvictionTrace:
    def test_no_eviction_trace_when_capacity_not_exceeded(self) -> None:
        """容量に余裕があるうちは EVICTED trace は 1 件も出ない。"""
        store = InMemoryPendingPredictionStore(capacity=8)
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)

        record_pending_prediction_if_applicable(
            pending_prediction_store=store,
            pending_prediction_enabled=True,
            being_id=_BEING,
            episode=_episode_with_draft("ep-1"),
            current_tick_provider=lambda: 10,
            trace_recorder=recorder,
        )

        evicted = [
            ev for ev in captured if ev.kind == TraceEventKind.PENDING_PREDICTION_EVICTED
        ]
        assert evicted == []

    def test_eviction_trace_emitted_when_store_evicts_oldest(self) -> None:
        """容量あふれで最古の約束が evict されたら EVICTED trace が 1 件残る。"""
        store = InMemoryPendingPredictionStore(capacity=1)
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)

        # 1 件目: 容量ちょうどで evict は起きない。
        record_pending_prediction_if_applicable(
            pending_prediction_store=store,
            pending_prediction_enabled=True,
            being_id=_BEING,
            episode=_episode_with_draft("ep-1"),
            current_tick_provider=lambda: 10,
            trace_recorder=recorder,
        )
        first_pending_id = store.list_all_by_being(_BEING)[0].pending_id

        # 2 件目: 容量あふれで 1 件目が evict される。
        record_pending_prediction_if_applicable(
            pending_prediction_store=store,
            pending_prediction_enabled=True,
            being_id=_BEING,
            episode=_episode_with_draft("ep-2"),
            current_tick_provider=lambda: 20,
            trace_recorder=recorder,
        )

        evicted = [
            ev for ev in captured if ev.kind == TraceEventKind.PENDING_PREDICTION_EVICTED
        ]
        assert len(evicted) == 1
        payload = evicted[0].payload
        assert payload["pending_id"] == first_pending_id
        assert payload["being_id"] == str(_BEING.value)
        assert payload["origin_episode_id"] == "ep-1"
        # evict が起きた現在 tick (= 2 件目を積んだ tick) が使われる。
        assert evicted[0].tick == 20

    def test_missing_trace_recorder_does_not_raise_on_eviction(self) -> None:
        """trace_recorder が None のときも evict 自体は起きて例外を投げない。"""
        store = InMemoryPendingPredictionStore(capacity=1)

        record_pending_prediction_if_applicable(
            pending_prediction_store=store,
            pending_prediction_enabled=True,
            being_id=_BEING,
            episode=_episode_with_draft("ep-1"),
            current_tick_provider=lambda: 10,
        )
        record_pending_prediction_if_applicable(
            pending_prediction_store=store,
            pending_prediction_enabled=True,
            being_id=_BEING,
            episode=_episode_with_draft("ep-2"),
            current_tick_provider=lambda: 20,
        )

        rows = store.list_all_by_being(_BEING)
        assert [p.origin_episode_id for p in rows] == ["ep-2"]
