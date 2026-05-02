"""MemoryContextPack の構築・不変条件・型検証のテスト。"""

from datetime import datetime

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    LongTermFactEntry,
    MemoryLawEntry,
    SubjectiveEpisode,
    SubjectiveFelt,
    SubjectivePredictionError,
)
from ai_rpg_world.application.llm.contracts.memory_context_pack import MemoryContextPack


def _episode(episode_id: str) -> SubjectiveEpisode:
    t0 = datetime(2026, 5, 1, 12, 0, 0)
    return SubjectiveEpisode(
        episode_id=episode_id,
        agent_id=1,
        created_at=t0,
        started_at_tick=None,
        ended_at_tick=None,
        source_trace_ids=("action:a1",),
        observed="x",
        interpreted="y",
        felt=SubjectiveFelt(primary_emotion="neutral", secondary_emotions=(), emotion_note=""),
        intended="i",
        expected="e",
        prediction_error=SubjectivePredictionError(level="none", reason="r"),
        cue_keys=(),
        cues=(),
        candidate_id="c1",
    )


def test_empty_pack() -> None:
    p = MemoryContextPack()
    assert p.current_situation == ""
    assert p.focus_episode is None
    assert p.temporal_neighbors == ()
    assert p.associative_neighbors == ()
    assert p.co_recalled_memories == ()
    assert p.semantic_facts == ()
    assert p.semantic_laws == ()
    assert p.contradictions == ()


def test_pack_with_neighbors_and_semantic() -> None:
    ep0 = _episode("e0")
    ep1 = _episode("e1")
    now = datetime(2026, 5, 1, 12, 0, 0)
    fact = LongTermFactEntry(id="f1", content="trap", player_id=1, updated_at=now)
    law = MemoryLawEntry(
        id="l1", subject="door", relation="may_have", target="trap", strength=0.5, player_id=1
    )
    p = MemoryContextPack(
        current_situation="spot 12",
        current_goals="開ける",
        current_attention="鍵穴",
        focus_episode=ep0,
        temporal_neighbors=(ep1,),
        associative_neighbors=(),
        semantic_facts=(fact,),
        semantic_laws=(law,),
        identity_context="慎重派",
        contradictions=("以前は扉だけで足りると思っていた",),
        co_recalled_memories=(),
    )
    assert p.focus_episode is ep0
    assert p.temporal_neighbors == (ep1,)
    assert p.semantic_facts == (fact,)
    assert p.semantic_laws == (law,)


def test_contradictions_empty_string_rejected() -> None:
    with pytest.raises(ValueError, match="contradictions entries"):
        MemoryContextPack(contradictions=("  ",))


def test_focus_episode_wrong_type_raises() -> None:
    with pytest.raises(TypeError, match="focus_episode"):
        MemoryContextPack(focus_episode="nope")  # type: ignore[arg-type]


def test_neighbors_wrong_element_type_raises() -> None:
    with pytest.raises(TypeError, match="temporal_neighbors"):
        MemoryContextPack(temporal_neighbors=(object(),))  # type: ignore[arg-type]


def test_semantic_facts_wrong_element_raises() -> None:
    with pytest.raises(TypeError, match="semantic_facts"):
        MemoryContextPack(semantic_facts=(object(),))  # type: ignore[list-item]


def test_semantic_laws_wrong_element_raises() -> None:
    with pytest.raises(TypeError, match="semantic_laws"):
        MemoryContextPack(semantic_laws=(42,))  # type: ignore[list-item]
