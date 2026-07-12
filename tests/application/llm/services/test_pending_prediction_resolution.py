"""resolve_pending_predictions_if_applicable (U10b 清算) の挙動を保証する。

U10b (予測誤差統一設計 部品6・pending prediction 清算):

- 履行 (fulfilled) / 破棄 (broken) 判定は PENDING_RESOLUTION evidence に
  転記され、決着した約束は store から除かれる
- tick_to を過ぎても決着しなかった約束は黙って失効し store から除かれる
- flag OFF / store 未配線 / being 未解決なら何もしない (導入前と一致)
- transcriber 未配線でも store の後始末 (清算・失効) は行う
"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.llm.services._pending_prediction_resolution import (
    resolve_pending_predictions_if_applicable,
)
from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
    BeliefEvidenceTranscriber,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
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
    PendingPrediction,
    PendingResolutionVerdict,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)

_BEING = BeingId("being-1")


def _pending(
    pending_id: str, *, tick_from: int, tick_to: int, cues=("player:カイト",), kind="promise"
) -> PendingPrediction:
    return PendingPrediction(
        pending_id=pending_id,
        text=f"約束-{pending_id}",
        resolution_cues=tuple(cues),
        tick_from=tick_from,
        tick_to=tick_to,
        origin_episode_id="ep-origin",
        created_tick=tick_from,
        kind=kind,
    )


def _episode(verdicts=()) -> SubjectiveEpisode:
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
        pending_resolution_verdicts=tuple(verdicts),
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


def _resolve(*, store, episode, transcriber=None, current_tick=20, enabled=True, being=_BEING, recorder=None):
    resolve_pending_predictions_if_applicable(
        pending_prediction_store=store,
        pending_prediction_enabled=enabled,
        being_id=being,
        episode=episode,
        belief_evidence_transcriber=transcriber,
        current_tick_provider=(lambda: current_tick),
        trace_recorder=recorder,
    )


class TestResolutionTranscription:
    """LLM 判定を evidence に転記し store から除く。"""

    def test_fulfilled_verdict_records_low_support_and_removes_pending(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("p1", tick_from=10, tick_to=25))
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")])

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        assert store.list_all_by_being(_BEING) == []
        evidences = buffer.list_all_by_being(_BEING)
        assert len(evidences) == 1
        ev = evidences[0]
        assert ev.source_kind is BeliefEvidenceSourceKind.PENDING_RESOLUTION
        assert ev.salience == "low"
        assert "果たされた" in ev.text
        # 人物 cue に寄せる
        assert ev.cue_signature == "player:カイト"

    def test_broken_verdict_records_high_contradiction(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("p1", tick_from=10, tick_to=25))
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        episode = _episode([PendingResolutionVerdict("p1", "broken")])

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        ev = buffer.list_all_by_being(_BEING)[0]
        assert ev.salience == "high"
        assert "破られた" in ev.text
        assert store.list_all_by_being(_BEING) == []

    def test_verdict_for_unknown_pending_id_is_ignored(self) -> None:
        """store に無い pending_id の判定は転記も除去もしない。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("p1", tick_from=10, tick_to=25))
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        episode = _episode([PendingResolutionVerdict("ghost", "fulfilled")])

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        assert buffer.list_all_by_being(_BEING) == []
        assert len(store.list_all_by_being(_BEING)) == 1

    def test_resolved_trace_emitted(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("p1", tick_from=10, tick_to=25))
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        episode = _episode([PendingResolutionVerdict("p1", "broken")])

        _resolve(
            store=store,
            episode=episode,
            transcriber=transcriber,
            current_tick=20,
            recorder=recorder,
        )

        kinds = [ev.kind for ev in captured]
        assert TraceEventKind.PENDING_PREDICTION_RESOLVED in kinds

    def test_resolved_trace_carries_pending_kind(self) -> None:
        """P11: RESOLVED trace の payload に種別 (pending_kind) が載る。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("p1", tick_from=10, tick_to=25, cues=("spot:3",), kind="plan")
        )
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        episode = _episode([PendingResolutionVerdict("p1", "broken")])

        _resolve(
            store=store,
            episode=episode,
            transcriber=transcriber,
            current_tick=20,
            recorder=recorder,
        )

        resolved = [
            ev for ev in captured if ev.kind == TraceEventKind.PENDING_PREDICTION_RESOLVED
        ]
        assert len(resolved) == 1
        assert resolved[0].payload["pending_kind"] == "plan"


class TestExpiry:
    """tick_to を過ぎた未決着の約束は黙って失効する。"""

    def test_expired_pending_is_removed_silently(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("old", tick_from=1, tick_to=5))
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        episode = _episode()  # 判定なし

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        assert store.list_all_by_being(_BEING) == []
        # 失効は evidence を積まない (黙って消える)
        assert buffer.list_all_by_being(_BEING) == []

    def test_pending_within_window_is_kept(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("live", tick_from=10, tick_to=30))
        episode = _episode()

        _resolve(store=store, episode=episode, current_tick=20)

        assert len(store.list_all_by_being(_BEING)) == 1

    def test_expired_trace_emitted(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("old", tick_from=1, tick_to=5))
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)

        _resolve(store=store, episode=_episode(), current_tick=20, recorder=recorder)

        kinds = [ev.kind for ev in captured]
        assert TraceEventKind.PENDING_PREDICTION_EXPIRED in kinds

    def test_expired_trace_carries_pending_kinds(self) -> None:
        """P11: EXPIRED trace の payload に id→種別 (pending_kinds) が載る

        (CREATED / RESOLVED と揃え、方針予測の失効を約束の失効と区別する)。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("plan1", tick_from=1, tick_to=5, cues=("spot:3",), kind="plan")
        )
        store.add_by_being(_BEING, _pending("prom1", tick_from=1, tick_to=5))
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)

        _resolve(store=store, episode=_episode(), current_tick=20, recorder=recorder)

        expired = [
            ev for ev in captured if ev.kind == TraceEventKind.PENDING_PREDICTION_EXPIRED
        ]
        assert len(expired) == 1
        assert expired[0].payload["pending_kinds"] == {"plan1": "plan", "prom1": "promise"}


class TestSafeDegradation:
    def test_flag_off_is_noop(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("old", tick_from=1, tick_to=5))
        episode = _episode([PendingResolutionVerdict("old", "broken")])

        _resolve(store=store, episode=episode, current_tick=20, enabled=False)

        # 何も除かれない (清算も失効もしない)
        assert len(store.list_all_by_being(_BEING)) == 1

    def test_store_none_is_noop(self) -> None:
        # 例外を投げずに黙って返る
        _resolve(store=None, episode=_episode(), current_tick=20)

    def test_being_none_is_noop(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("old", tick_from=1, tick_to=5))
        _resolve(store=store, episode=_episode(), current_tick=20, being=None)
        assert len(store.list_all_by_being(_BEING)) == 1

    def test_transcriber_none_still_prunes(self) -> None:
        """evidence 経路が OFF でも、決着・失効による store 後始末は行う。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("p1", tick_from=10, tick_to=25))
        store.add_by_being(_BEING, _pending("old", tick_from=1, tick_to=5))
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")])

        _resolve(store=store, episode=episode, transcriber=None, current_tick=20)

        # p1 は清算で、old は失効で除かれる
        assert store.list_all_by_being(_BEING) == []
