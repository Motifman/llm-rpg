"""Episode encoding（Phase 3）の結合・LLM JSON パース・ストアのテスト。"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionExperienceTrace,
    EpisodeCandidate,
    EpisodeEncodingContextDto,
    ObservationExperienceTrace,
)
from ai_rpg_world.application.llm.contracts.interfaces import IEpisodeEncoder
from ai_rpg_world.application.llm.exceptions import EpisodeEncodingException
from ai_rpg_world.application.llm.services.episode_encoding_processor import (
    EpisodeEncodingProcessor,
)
from ai_rpg_world.application.llm.services.experience_trace_bundle_resolver import (
    ExperienceTraceBundleResolver,
)
from ai_rpg_world.application.llm.services.in_memory_action_experience_trace_store import (
    InMemoryActionExperienceTraceStore,
)
from ai_rpg_world.application.llm.services.in_memory_episode_candidate_store import (
    InMemoryEpisodeCandidateStore,
)
from ai_rpg_world.application.llm.services.in_memory_observation_experience_trace_store import (
    InMemoryObservationExperienceTraceStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.llm_json_episode_encoder import (
    LlmJsonEpisodeEncoder,
    subjective_episode_from_llm_dict,
)
from ai_rpg_world.application.llm.services.stub_episode_encoder import StubEpisodeEncoder
from ai_rpg_world.application.llm.services.stub_episode_encoding_llm_port import (
    StubEpisodeEncodingLlmPort,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _action_trace(tid: str, agent_id: int = 1, at: datetime | None = None) -> ActionExperienceTrace:
    return ActionExperienceTrace(
        trace_id=tid,
        agent_id=agent_id,
        occurred_at=at or datetime.now(),
        tool_name="spot_graph_look",
        tool_args={},
        inner_thought="試す。",
        intention="周辺を確認する。",
        expected_result="状況が分かる。",
        attention="扉",
        emotion_hint="curiosity",
        tool_result="周囲に異常なし。",
        result_success=True,
    )


def _observation_trace(tid: str, at: datetime | None = None) -> ObservationExperienceTrace:
    return ObservationExperienceTrace(
        trace_id=tid,
        agent_id=1,
        occurred_at=at or datetime.now(),
        observation_summary="遠くで物音がした。",
        observation_kind="world_event",
        structured={"kind": "noise"},
    )


def _candidate(
    cid: str,
    source_ids: tuple[str, ...],
    *,
    created_at: datetime | None = None,
    status: str = "pending_encoding",
    subjective_episode_id: str | None = None,
    encoding_error: str | None = None,
) -> EpisodeCandidate:
    t0 = created_at or datetime.now()
    return EpisodeCandidate(
        candidate_id=cid,
        agent_id=1,
        created_at=t0,
        source_trace_ids=source_ids,
        started_at=t0,
        ended_at=t0,
        trace_count=len(source_ids),
        boundary_score=10,
        boundary_reasons=("boundary_test",),
        status=status,  # type: ignore[arg-type]
        subjective_episode_id=subjective_episode_id,
        encoding_error=encoding_error,
    )


def _processor(
    candidate_store: InMemoryEpisodeCandidateStore,
    action_store: InMemoryActionExperienceTraceStore,
    observation_store: InMemoryObservationExperienceTraceStore,
    episode_store: InMemorySubjectiveEpisodeStore,
    encoder: IEpisodeEncoder,
    *,
    max_retries: int = 2,
    max_queue_retries: int = 0,
    encoding_backoff_base_seconds: float = 2.0,
    utc_now=None,
) -> EpisodeEncodingProcessor:
    resolver = ExperienceTraceBundleResolver(action_store, observation_store)
    ctx = EpisodeEncodingContextDto(current_beliefs="room is dark")
    kwargs = dict(
        candidate_store=candidate_store,
        trace_resolver=resolver,
        subjective_episode_store=episode_store,
        encoder=encoder,
        context_provider=lambda _pid: ctx,
        max_retries=max_retries,
        max_queue_retries=max_queue_retries,
        encoding_backoff_base_seconds=encoding_backoff_base_seconds,
    )
    if utc_now is not None:
        kwargs["utc_now"] = utc_now
    return EpisodeEncodingProcessor(**kwargs)


def test_resolver_restores_action_and_observation_in_order() -> None:
    pid = PlayerId(1)
    t0 = datetime.now()
    action_store = InMemoryActionExperienceTraceStore()
    obs_store = InMemoryObservationExperienceTraceStore()
    action_store.append(pid, _action_trace("a1", at=t0))
    obs_store.append(pid, _observation_trace("o1", at=t0 + timedelta(seconds=1)))
    resolver = ExperienceTraceBundleResolver(action_store, obs_store)
    got = resolver.resolve_ordered(
        pid, ("action:a1", "observation:o1")
    )
    assert len(got) == 2
    assert isinstance(got[0], ActionExperienceTrace) and got[0].trace_id == "a1"
    assert isinstance(got[1], ObservationExperienceTrace) and got[1].trace_id == "o1"


def test_resolver_missing_trace_raises() -> None:
    pid = PlayerId(1)
    stores = InMemoryActionExperienceTraceStore(), InMemoryObservationExperienceTraceStore()
    resolver = ExperienceTraceBundleResolver(*stores)
    with pytest.raises(ValueError, match="missing action trace"):
        resolver.resolve_ordered(pid, ("action:ghost",))


def test_resolver_invalid_prefix_raises() -> None:
    pid = PlayerId(1)
    stores = InMemoryActionExperienceTraceStore(), InMemoryObservationExperienceTraceStore()
    resolver = ExperienceTraceBundleResolver(*stores)
    with pytest.raises(ValueError, match="action: or observation:"):
        resolver.resolve_ordered(pid, ("raw-id",))


def test_action_store_find_by_trace_id() -> None:
    pid = PlayerId(1)
    store = InMemoryActionExperienceTraceStore()
    store.append(pid, _action_trace("x1"))
    assert store.find_by_trace_id(pid, "x1") is not None
    assert store.find_by_trace_id(pid, "none") is None


def test_candidate_store_list_pending_and_get_replace() -> None:
    pid = PlayerId(1)
    store = InMemoryEpisodeCandidateStore()
    c1 = _candidate("p1", ("action:a",), created_at=datetime(2025, 1, 1, 12, 0, 0))
    c2 = _candidate("p2", ("action:b",), created_at=datetime(2025, 1, 1, 11, 0, 0))
    store.add(pid, c1)
    store.add(pid, c2)
    pending = store.list_pending_encoding(pid, limit=10)
    assert [c.candidate_id for c in pending] == ["p2", "p1"]
    updated = _candidate(
        "p1",
        ("action:a",),
        created_at=c1.created_at,
        status="encoded",
        subjective_episode_id="ep-1",
    )
    store.replace_candidate(pid, updated)
    assert store.get_by_candidate_id(pid, "p1") == updated
    pending2 = store.list_pending_encoding(pid, limit=10)
    assert len(pending2) == 1 and pending2[0].candidate_id == "p2"


def test_processor_stub_andencode_updates_candidate_and_store() -> None:
    pid = PlayerId(1)
    cstore = InMemoryEpisodeCandidateStore()
    astore = InMemoryActionExperienceTraceStore()
    ostore = InMemoryObservationExperienceTraceStore()
    estate = InMemorySubjectiveEpisodeStore()
    astore.append(pid, _action_trace("tid"))
    cand = _candidate("cand-1", ("action:tid",))
    cstore.add(pid, cand)
    proc = _processor(cstore, astore, ostore, estate, StubEpisodeEncoder())
    assert proc.process_pending(pid) == 1
    after = cstore.get_by_candidate_id(pid, "cand-1")
    assert after is not None
    assert after.status == "encoded"
    assert after.subjective_episode_id
    ep = estate.get_by_episode_id(pid, after.subjective_episode_id)
    assert ep is not None
    assert ep.candidate_id == "cand-1"
    assert "spot_graph_look" in ep.observed


def test_processor_second_run_does_not_reencode() -> None:
    pid = PlayerId(1)
    cstore = InMemoryEpisodeCandidateStore()
    astore = InMemoryActionExperienceTraceStore()
    ostore = InMemoryObservationExperienceTraceStore()
    estate = InMemorySubjectiveEpisodeStore()
    astore.append(pid, _action_trace("tid"))
    cstore.add(pid, _candidate("c1", ("action:tid",)))
    proc = _processor(cstore, astore, ostore, estate, StubEpisodeEncoder())
    assert proc.process_pending(pid) == 1
    assert proc.process_pending(pid) == 0


def test_processor_missing_trace_marks_encoding_failed() -> None:
    pid = PlayerId(1)
    cstore = InMemoryEpisodeCandidateStore()
    astore = InMemoryActionExperienceTraceStore()
    ostore = InMemoryObservationExperienceTraceStore()
    estate = InMemorySubjectiveEpisodeStore()
    cstore.add(pid, _candidate("c1", ("action:nope",)))
    proc = _processor(cstore, astore, ostore, estate, StubEpisodeEncoder())
    assert proc.process_pending(pid) == 0
    after = cstore.get_by_candidate_id(pid, "c1")
    assert after is not None and after.status == "encoding_failed"
    assert after.encoding_error


class _AlwaysFailingEncoder(IEpisodeEncoder):
    def encode(self, context, candidate, traces):
        raise EpisodeEncodingException("fail", candidate_id=candidate.candidate_id)


def test_processor_encoder_failure_marks_encoding_failed() -> None:
    pid = PlayerId(1)
    cstore = InMemoryEpisodeCandidateStore()
    astore = InMemoryActionExperienceTraceStore()
    ostore = InMemoryObservationExperienceTraceStore()
    estate = InMemorySubjectiveEpisodeStore()
    astore.append(pid, _action_trace("tid"))
    cstore.add(pid, _candidate("c1", ("action:tid",)))
    proc = _processor(
        cstore,
        astore,
        ostore,
        estate,
        _AlwaysFailingEncoder(),
        max_retries=2,
        max_queue_retries=0,
    )
    assert proc.process_pending(pid) == 0
    after = cstore.get_by_candidate_id(pid, "c1")
    assert after is not None and after.status == "encoding_failed"


def test_processor_encoder_transient_failure_backoff_then_permanent() -> None:
    pid = PlayerId(1)
    cstore = InMemoryEpisodeCandidateStore()
    astore = InMemoryActionExperienceTraceStore()
    ostore = InMemoryObservationExperienceTraceStore()
    estate = InMemorySubjectiveEpisodeStore()
    astore.append(pid, _action_trace("tid"))
    cstore.add(pid, _candidate("c1", ("action:tid",)))
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    clock = {"now": t0}

    def utc_now():
        return clock["now"]

    proc = _processor(
        cstore,
        astore,
        ostore,
        estate,
        _AlwaysFailingEncoder(),
        max_retries=1,
        max_queue_retries=2,
        encoding_backoff_base_seconds=10.0,
        utc_now=utc_now,
    )
    assert proc.process_pending(pid) == 0
    mid = cstore.get_by_candidate_id(pid, "c1")
    assert mid is not None and mid.status == "pending_encoding"
    assert mid.encoding_retry_count == 1
    assert mid.last_encoding_failure_at == t0

    assert proc.process_pending(pid) == 0
    assert cstore.get_by_candidate_id(pid, "c1") == mid

    clock["now"] = t0 + timedelta(seconds=15)
    assert proc.process_pending(pid) == 0
    mid2 = cstore.get_by_candidate_id(pid, "c1")
    assert mid2 is not None and mid2.encoding_retry_count == 2

    clock["now"] = t0 + timedelta(seconds=40)
    assert proc.process_pending(pid) == 0
    final = cstore.get_by_candidate_id(pid, "c1")
    assert final is not None and final.status == "encoding_failed"


def test_llm_json_encoder_applies_rule_cues() -> None:
    payload = {
        "observed": "見えた。",
        "interpreted": "危ない。",
        "intended": "下がる。",
        "expected": "安全。",
        "felt": {"primary_emotion": "fear", "secondary_emotions": [], "emotion_note": ""},
        "prediction_error": {"level": "medium", "reason": "勘違い"},
        "belief_update_candidates": [],
        "relationship_deltas": [],
        "cue_keys": ["door"],
        "importance": "high",
        "confidence": "low",
    }
    llm = StubEpisodeEncodingLlmPort(json.dumps(payload, ensure_ascii=False))
    encoder = LlmJsonEpisodeEncoder(llm)
    cand = _candidate("lc", ("action:a1",))
    ctx = EpisodeEncodingContextDto()
    trace = _action_trace("a1")
    ep = encoder.encode(ctx, cand, (trace,))
    assert ep.observed == "見えた。"
    assert ep.felt.primary_emotion == "fear"
    assert ep.cue_keys == ()
    assert any(c.to_canonical() == "action:spot_graph_look" for c in ep.cues)
    assert llm.calls


def test_llm_json_encoder_invalid_json_raises() -> None:
    llm = StubEpisodeEncodingLlmPort("not-json")
    encoder = LlmJsonEpisodeEncoder(llm)
    cand = _candidate("lc", ("action:a1",))
    with pytest.raises(EpisodeEncodingException, match="invalid JSON"):
        encoder.encode(
            EpisodeEncodingContextDto(), cand, (_action_trace("a1"),)
        )


def test_subjective_episode_from_llm_dict_rejects_mismatched_source_trace_ids() -> None:
    cand = _candidate("x", ("action:a", "observation:o"))
    bad = {
        "observed": "a",
        "interpreted": "b",
        "intended": "c",
        "expected": "d",
        "felt": {
            "primary_emotion": "neutral",
            "secondary_emotions": [],
            "emotion_note": "",
        },
        "source_trace_ids": ["action:a"],
    }
    with pytest.raises(EpisodeEncodingException, match="source_trace_ids must match"):
        subjective_episode_from_llm_dict(bad, cand)


def test_subjective_episode_from_llm_dict_rejects_invalid_emotion_label() -> None:
    cand = _candidate("x", ("action:a1",))
    bad = {
        "observed": "a",
        "interpreted": "b",
        "intended": "c",
        "expected": "d",
        "felt": {
            "primary_emotion": "警戒",
            "secondary_emotions": [],
            "emotion_note": "",
        },
        "prediction_error": {"level": "none", "reason": ""},
        "belief_update_candidates": [],
        "relationship_deltas": [],
        "cue_keys": ["x"],
        "importance": "medium",
        "confidence": "medium",
    }
    with pytest.raises(EpisodeEncodingException, match="felt.primary_emotion"):
        subjective_episode_from_llm_dict(bad, cand)


def test_subjective_episode_from_llm_dict_ignores_llm_cue_keys() -> None:
    cand = _candidate("x", ("action:a1",))
    data = {
        "observed": "見えた。",
        "interpreted": "危ない。",
        "intended": "下がる。",
        "expected": "安全。",
        "felt": {"primary_emotion": "fear", "secondary_emotions": [], "emotion_note": ""},
        "prediction_error": {"level": "medium", "reason": "勘違い"},
        "belief_update_candidates": [],
        "relationship_deltas": [],
        "cue_keys": ["llm_should_not_be_used"],
        "importance": "high",
        "confidence": "low",
    }
    ep = subjective_episode_from_llm_dict(data, cand)
    assert ep.cue_keys == ()


def test_subjective_episode_from_llm_dict_cue_keys_wrong_type_raises() -> None:
    cand = _candidate("x", ("action:a1",))
    bad = {
        "observed": "a",
        "interpreted": "b",
        "intended": "c",
        "expected": "d",
        "felt": {"primary_emotion": "neutral", "secondary_emotions": [], "emotion_note": ""},
        "prediction_error": {"level": "none", "reason": ""},
        "belief_update_candidates": [],
        "relationship_deltas": [],
        "cue_keys": "not-a-list",
        "importance": "medium",
        "confidence": "medium",
    }
    with pytest.raises(EpisodeEncodingException, match="cue_keys must be list"):
        subjective_episode_from_llm_dict(bad, cand)
