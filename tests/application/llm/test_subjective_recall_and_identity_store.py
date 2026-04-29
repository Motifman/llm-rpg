"""SubjectiveMemoryRecallExecutor と Identity ストアの軽いテスト。"""

from ai_rpg_world.application.llm.contracts.dtos import (
    SubjectiveEpisode,
    SubjectiveFelt,
    SubjectivePredictionError,
)
from ai_rpg_world.application.llm.services.in_memory_identity_memory_store import (
    InMemoryIdentityMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.subjective_memory_recall_executor import (
    SubjectiveMemoryRecallExecutor,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _ep(eid: str, observed: str) -> SubjectiveEpisode:
    from datetime import datetime

    return SubjectiveEpisode(
        episode_id=eid,
        agent_id=1,
        created_at=datetime.now(),
        started_at_tick=None,
        ended_at_tick=None,
        source_trace_ids=("a",),
        observed=observed,
        interpreted="",
        felt=SubjectiveFelt(primary_emotion="neutral", secondary_emotions=(), emotion_note=""),
        intended="",
        expected="",
        prediction_error=SubjectivePredictionError(level="none", reason=""),
        importance="high",  # type: ignore[arg-type]
        salience_reasons=(),
        candidate_id="c",
    )


def test_subjective_recall_executor_keyword_filter() -> None:
    store = InMemorySubjectiveEpisodeStore()
    pid = PlayerId(1)
    store.put(pid, _ep("e-a", "赤い扉を見た"))
    store.put(pid, _ep("e-b", "青い空だった"))
    ex = SubjectiveMemoryRecallExecutor(subjective_episode_store=store)
    out = ex.execute(pid, keywords="赤い", limit=5)
    assert "e-a" in out
    assert "e-b" not in out


def test_count_reflection_journal_entries() -> None:
    store = InMemorySubjectiveEpisodeStore()
    pid = PlayerId(1)
    assert store.count_reflection_journal_entries(pid) == 0
    from dataclasses import replace
    from datetime import datetime, timezone

    from ai_rpg_world.application.llm.contracts.dtos import (
        MemoryReflectionEpisodePatchDto,
        MemoryReflectionJournalEntry,
    )

    ep = _ep("e1", "x")
    entry = MemoryReflectionJournalEntry(
        entry_id="j1",
        created_at=datetime.now(timezone.utc),
        correlation_id="c",
        trigger="passive_recall",
        recall_trigger="t",
        current_interpretation="i",
        effect_on_decision="d",
        episode_patch=MemoryReflectionEpisodePatchDto(),
    )
    store.put(pid, replace(ep, memory_reflection_journal=(entry,)))
    assert store.count_reflection_journal_entries(pid) == 1


def test_identity_memory_store_roundtrip() -> None:
    store = InMemoryIdentityMemoryStore()
    pid = PlayerId(2)
    store.append_statement(pid, "自分は慎重派だ", source_note="reflection")
    got = store.list_statements(pid, 10)
    assert len(got) == 1
    assert "慎重派" in got[0]
    assert "reflection" in got[0]
