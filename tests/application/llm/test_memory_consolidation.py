"""Memory Consolidation（ジャーナル → 長期事実・Identity）のテスト。"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.dtos import (
    MemoryReflectionIdentityCandidateDto,
    MemoryReflectionEpisodePatchDto,
    MemoryReflectionJournalEntry,
    MemoryReflectionSemanticCandidateDto,
    SubjectiveEpisode,
    SubjectiveFelt,
    SubjectivePredictionError,
)
from ai_rpg_world.application.llm.services.in_memory_identity_memory_store import (
    InMemoryIdentityMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.memory_consolidation_runner import (
    InMemoryConsolidationCheckpoint,
    MemoryConsolidationRunner,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _journal_entry(
    entry_id: str,
    *,
    semantic: tuple[MemoryReflectionSemanticCandidateDto, ...] = (),
    identity: tuple[MemoryReflectionIdentityCandidateDto, ...] = (),
) -> MemoryReflectionJournalEntry:
    return MemoryReflectionJournalEntry(
        entry_id=entry_id,
        created_at=datetime.now(timezone.utc),
        correlation_id="c",
        trigger="passive_recall",
        recall_trigger="t",
        current_interpretation="i",
        effect_on_decision="d",
        episode_patch=MemoryReflectionEpisodePatchDto(),
        semantic_update_candidates=semantic,
        identity_update_candidates=identity,
    )


def _episode(
    episode_id: str, journal: tuple[MemoryReflectionJournalEntry, ...]
) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        agent_id=1,
        created_at=datetime.now(timezone.utc),
        started_at_tick=None,
        ended_at_tick=None,
        source_trace_ids=("a",),
        observed="o",
        interpreted="",
        felt=SubjectiveFelt(primary_emotion="neutral", secondary_emotions=(), emotion_note=""),
        intended="",
        expected="",
        prediction_error=SubjectivePredictionError(level="none", reason=""),
        memory_reflection_journal=journal,
        importance="medium",  # type: ignore[arg-type]
        salience_reasons=(),
        candidate_id="c",
    )


def test_consolidation_disabled_when_journal_threshold_zero() -> None:
    pid = PlayerId(1)
    episodes = InMemorySubjectiveEpisodeStore()
    long_term = InMemoryLongTermMemoryStore()
    identity = InMemoryIdentityMemoryStore()
    cp = InMemoryConsolidationCheckpoint()
    episodes.put(
        pid,
        _episode(
            "e1",
            (
                _journal_entry(
                    "j1",
                    semantic=(
                        MemoryReflectionSemanticCandidateDto(summary="世界は広い"),
                    ),
                ),
            ),
        ),
    )
    runner = MemoryConsolidationRunner(
        subjective_episode_store=episodes,
        long_term_memory_store=long_term,
        identity_memory_store=identity,
        checkpoint=cp,
        journal_threshold=0,
    )
    runner.run(pid)
    assert long_term.search_facts(pid, limit=10) == []
    assert identity.list_statements(pid, 10) == ()


def test_consolidation_skips_until_journal_count_reaches_threshold() -> None:
    pid = PlayerId(1)
    episodes = InMemorySubjectiveEpisodeStore()
    long_term = InMemoryLongTermMemoryStore()
    identity = InMemoryIdentityMemoryStore()
    cp = InMemoryConsolidationCheckpoint()
    runner = MemoryConsolidationRunner(
        subjective_episode_store=episodes,
        long_term_memory_store=long_term,
        identity_memory_store=identity,
        checkpoint=cp,
        journal_threshold=3,
    )
    for i in range(1, 3):
        episodes.put(
            pid,
            _episode(
                f"e{i}",
                (
                    _journal_entry(
                        f"j{i}",
                        semantic=(MemoryReflectionSemanticCandidateDto(summary=f"s{i}"),),
                    ),
                ),
            ),
        )
    runner.run(pid)
    assert long_term.search_facts(pid, limit=20) == []

    episodes.put(
        pid,
        _episode(
            "e3",
            (
                _journal_entry(
                    "j3",
                    semantic=(MemoryReflectionSemanticCandidateDto(summary="s3"),),
                ),
            ),
        ),
    )
    runner.run(pid)
    facts = long_term.search_facts(pid, limit=20)
    assert len(facts) == 3
    contents = {f.content for f in facts}
    assert "[consolidation:semantic] s1" in contents
    assert "[consolidation:semantic] s2" in contents
    assert "[consolidation:semantic] s3" in contents


def test_consolidation_writes_identity_and_is_idempotent() -> None:
    pid = PlayerId(1)
    episodes = InMemorySubjectiveEpisodeStore()
    long_term = InMemoryLongTermMemoryStore()
    identity = InMemoryIdentityMemoryStore()
    cp = InMemoryConsolidationCheckpoint()
    runner = MemoryConsolidationRunner(
        subjective_episode_store=episodes,
        long_term_memory_store=long_term,
        identity_memory_store=identity,
        checkpoint=cp,
        journal_threshold=1,
    )
    episodes.put(
        pid,
        _episode(
            "e1",
            (
                _journal_entry(
                    "jx",
                    semantic=(MemoryReflectionSemanticCandidateDto(summary="事実A", note="n1"),),
                    identity=(
                        MemoryReflectionIdentityCandidateDto(
                            summary="自分は探索者だ", note=""
                        ),
                    ),
                ),
            ),
        ),
    )
    runner.run(pid)
    assert len(long_term.search_facts(pid, limit=10)) == 1
    stm = identity.list_statements(pid, 5)
    assert len(stm) == 1
    assert "探索者" in stm[0]
    assert "consolidation:jx" in stm[0]

    runner.run(pid)
    assert len(long_term.search_facts(pid, limit=10)) == 1
    assert len(identity.list_statements(pid, 5)) == 1


def test_new_journal_after_first_consolidation_runs_without_total_re_threshold() -> None:
    pid = PlayerId(1)
    episodes = InMemorySubjectiveEpisodeStore()
    long_term = InMemoryLongTermMemoryStore()
    identity = InMemoryIdentityMemoryStore()
    cp = InMemoryConsolidationCheckpoint()
    runner = MemoryConsolidationRunner(
        subjective_episode_store=episodes,
        long_term_memory_store=long_term,
        identity_memory_store=identity,
        checkpoint=cp,
        journal_threshold=2,
    )
    episodes.put(
        pid,
        _episode(
            "e1",
            (
                _journal_entry(
                    "a1",
                    semantic=(MemoryReflectionSemanticCandidateDto(summary="one"),),
                ),
                _journal_entry(
                    "a2",
                    semantic=(MemoryReflectionSemanticCandidateDto(summary="two"),),
                ),
            ),
        ),
    )
    runner.run(pid)
    assert len(long_term.search_facts(pid, limit=10)) == 2

    ep2 = _episode(
        "e2",
        (
            _journal_entry(
                "b1",
                semantic=(MemoryReflectionSemanticCandidateDto(summary="three"),),
            ),
        ),
    )
    episodes.put(pid, ep2)
    runner.run(pid)
    assert len(long_term.search_facts(pid, limit=10)) == 3


def test_empty_candidates_still_checkpointed() -> None:
    pid = PlayerId(1)
    episodes = InMemorySubjectiveEpisodeStore()
    long_term = InMemoryLongTermMemoryStore()
    identity = InMemoryIdentityMemoryStore()
    cp = InMemoryConsolidationCheckpoint()
    runner = MemoryConsolidationRunner(
        subjective_episode_store=episodes,
        long_term_memory_store=long_term,
        identity_memory_store=identity,
        checkpoint=cp,
        journal_threshold=1,
    )
    episodes.put(pid, _episode("e1", (_journal_entry("empty_only"),)))
    runner.run(pid)
    assert long_term.search_facts(pid, limit=10) == []
    runner.run(pid)
    assert long_term.search_facts(pid, limit=10) == []
