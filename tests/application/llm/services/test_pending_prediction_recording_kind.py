"""record_pending_prediction_if_applicable が draft の種別 (kind) を確定版の
PendingPrediction と CREATED trace に引き継ぐことを保証する (P11)。

U10a の記録経路 (draft → PendingPrediction) が P11 で追加した kind
(promise / plan) を落とさないことの回帰ガード。
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
    PENDING_KIND_PLAN,
    PendingPredictionDraft,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)

_BEING = BeingId("being-1")


def _episode_with_draft(kind: str) -> SubjectiveEpisode:
    draft = PendingPredictionDraft(
        text="浜を探索し続ければ山頂への道が分かるはず",
        resolution_cues=("spot:12",),
        tick_offset_from=2,
        tick_offset_to=6,
        kind=kind,
    )
    return SubjectiveEpisode(
        episode_id="ep-1",
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


class TestPendingRecordingCarriesKind:
    def test_plan_kind_is_carried_from_draft_to_stored_pending(self) -> None:
        store = InMemoryPendingPredictionStore()
        record_pending_prediction_if_applicable(
            pending_prediction_store=store,
            pending_prediction_enabled=True,
            being_id=_BEING,
            episode=_episode_with_draft("plan"),
            current_tick_provider=lambda: 15,
        )

        stored = store.list_all_by_being(_BEING)
        assert len(stored) == 1
        assert stored[0].kind == PENDING_KIND_PLAN
        # 相対オフセットが created_tick を足した絶対 tick に変換されている。
        assert stored[0].tick_from == 17
        assert stored[0].tick_to == 21

    def test_created_trace_carries_pending_kind(self) -> None:
        store = InMemoryPendingPredictionStore()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        record_pending_prediction_if_applicable(
            pending_prediction_store=store,
            pending_prediction_enabled=True,
            being_id=_BEING,
            episode=_episode_with_draft("plan"),
            current_tick_provider=lambda: 15,
            trace_recorder=recorder,
        )

        created = [
            ev for ev in captured if ev.kind == TraceEventKind.PENDING_PREDICTION_CREATED
        ]
        assert len(created) == 1
        assert created[0].payload["pending_kind"] == PENDING_KIND_PLAN
