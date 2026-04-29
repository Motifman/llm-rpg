"""Memory Reflection（主観エピソード再解釈）のパース・プロセッサ・スケジューラテスト。"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionExperienceTrace,
    EpisodeCandidate,
    EpisodeEncodingContextDto,
    SubjectiveEpisode,
    SubjectiveFelt,
    SubjectivePredictionError,
)
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
from ai_rpg_world.application.llm.services.memory_reflection_processor import (
    AFTER_SUBJECTIVE_ENCODE_TRIGGER,
    MemoryReflectionJob,
    SubjectiveMemoryReflectionProcessor,
)
from ai_rpg_world.application.llm.services.same_process_memory_reflection_scheduler import (
    SameProcessMemoryReflectionScheduler,
)
from ai_rpg_world.application.llm.services.stub_episode_encoder import StubEpisodeEncoder
from ai_rpg_world.application.llm.services.stub_memory_reflection_llm_port import (
    StubMemoryReflectionLlmPort,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _action_trace(tid: str) -> ActionExperienceTrace:
    return ActionExperienceTrace(
        trace_id=tid,
        agent_id=1,
        occurred_at=datetime.now(timezone.utc),
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


def _candidate(cid: str, source_ids: tuple[str, ...]) -> EpisodeCandidate:
    t0 = datetime.now(timezone.utc)
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
        status="pending_encoding",  # type: ignore[arg-type]
    )


def _minimal_reflection_json() -> str:
    return json.dumps(
        {
            "recall_trigger": "encoding 直後の再考察",
            "current_interpretation": "いま見ると試行の一環だった。",
            "effect_on_decision": "同種の局面では慎重に。",
            "episode_patch": {
                "emphasized": "結果の重み",
                "faded": "瞬間の不安",
                "new_meaning": "学習機会",
                "emotional_tone_shift": "やや落ち着き",
            },
            "semantic_update_candidates": [],
            "identity_update_candidates": [],
        },
        ensure_ascii=False,
    )


def _episode_stub(pid: int, eid: str, *, importance: str = "high") -> SubjectiveEpisode:
    t0 = datetime.now(timezone.utc)
    return SubjectiveEpisode(
        episode_id=eid,
        agent_id=pid,
        created_at=t0,
        started_at_tick=None,
        ended_at_tick=None,
        source_trace_ids=("action:x",),
        observed="見た",
        interpreted="考えた",
        felt=SubjectiveFelt(primary_emotion="neutral", secondary_emotions=(), emotion_note=""),
        intended="進む",
        expected="うまくいく",
        prediction_error=SubjectivePredictionError(level="none", reason=""),
        importance=importance,  # type: ignore[arg-type]
        salience_reasons=(),
        candidate_id="c",
    )


def test_memory_reflection_processor_appends_journal() -> None:
    pid = PlayerId(1)
    store = InMemorySubjectiveEpisodeStore()
    ep = _episode_stub(1, "ep-1")
    store.put(pid, ep)
    port = StubMemoryReflectionLlmPort(_minimal_reflection_json())
    proc = SubjectiveMemoryReflectionProcessor(
        subjective_episode_store=store,
        llm_port=port,
        context_provider=lambda _p: EpisodeEncodingContextDto(current_beliefs="x"),
        structured_json_output=False,
        utc_now=lambda: datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc),
    )
    job = MemoryReflectionJob(
        player_id=pid,
        episode_id=ep.episode_id,
        trigger=AFTER_SUBJECTIVE_ENCODE_TRIGGER,
        correlation_id="corr-a",
    )
    assert proc.run_once(job) is True
    loaded = store.get_by_episode_id(pid, ep.episode_id)
    assert loaded is not None
    assert len(loaded.memory_reflection_journal) == 1
    assert loaded.memory_reflection_journal[0].correlation_id == "corr-a"
    assert loaded.memory_reflection_journal[0].recall_trigger


def test_memory_reflection_processor_idempotent_skips_second() -> None:
    pid = PlayerId(1)
    store = InMemorySubjectiveEpisodeStore()
    ep = _episode_stub(1, "ep-2")
    store.put(pid, ep)
    port = StubMemoryReflectionLlmPort(_minimal_reflection_json())
    proc = SubjectiveMemoryReflectionProcessor(
        subjective_episode_store=store,
        llm_port=port,
        context_provider=lambda _p: EpisodeEncodingContextDto(),
        structured_json_output=False,
        utc_now=lambda: datetime.now(timezone.utc),
    )
    job = MemoryReflectionJob(
        player_id=pid,
        episode_id=ep.episode_id,
        trigger=AFTER_SUBJECTIVE_ENCODE_TRIGGER,
        correlation_id="c1",
    )
    assert proc.run_once(job) is True
    assert port.calls
    calls_before = len(port.calls)
    assert proc.run_once(job) is False
    assert len(port.calls) == calls_before


def test_scheduler_enqueue_deduplicates_same_key() -> None:
    pid = PlayerId(1)
    store = InMemorySubjectiveEpisodeStore()
    ep = _episode_stub(1, "ep-dedup")
    store.put(pid, ep)
    port = StubMemoryReflectionLlmPort(_minimal_reflection_json())
    proc = SubjectiveMemoryReflectionProcessor(
        subjective_episode_store=store,
        llm_port=port,
        context_provider=lambda _p: EpisodeEncodingContextDto(),
        structured_json_output=False,
    )
    sched = SameProcessMemoryReflectionScheduler(proc, max_attempts=1)
    job_a = MemoryReflectionJob(
        player_id=pid,
        episode_id=ep.episode_id,
        trigger=AFTER_SUBJECTIVE_ENCODE_TRIGGER,
        correlation_id="a",
    )
    job_b = MemoryReflectionJob(
        player_id=pid,
        episode_id=ep.episode_id,
        trigger=AFTER_SUBJECTIVE_ENCODE_TRIGGER,
        correlation_id="b",
    )
    assert sched.enqueue(job_a) is True
    assert sched.enqueue(job_b) is False
    for _ in range(200):
        got = store.get_by_episode_id(pid, ep.episode_id)
        if got and got.memory_reflection_journal:
            break
        time.sleep(0.01)
    sched.shutdown(wait=True, timeout=3.0)
    fin = store.get_by_episode_id(pid, ep.episode_id)
    assert fin is not None
    assert len(fin.memory_reflection_journal) == 1


def test_episode_encoding_processor_calls_after_encode_hook() -> None:
    pid = PlayerId(1)
    cstore = InMemoryEpisodeCandidateStore()
    astore = InMemoryActionExperienceTraceStore()
    ostore = InMemoryObservationExperienceTraceStore()
    estate = InMemorySubjectiveEpisodeStore()
    astore.append(pid, _action_trace("tid"))
    cstore.add(pid, _candidate("cand-hook", ("action:tid",)))
    seen: list[tuple[int, str]] = []

    def hook(p: PlayerId, ep: SubjectiveEpisode) -> None:
        seen.append((p.value, ep.episode_id))

    resolver = ExperienceTraceBundleResolver(astore, ostore)
    proc = EpisodeEncodingProcessor(
        candidate_store=cstore,
        trace_resolver=resolver,
        subjective_episode_store=estate,
        encoder=StubEpisodeEncoder(),
        context_provider=lambda _p: EpisodeEncodingContextDto(),
        on_subjective_episode_encoded=hook,
    )
    assert proc.process_pending(pid) == 1
    assert len(seen) == 1 and seen[0][0] == 1
