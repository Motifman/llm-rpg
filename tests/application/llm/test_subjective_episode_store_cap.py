"""InMemorySubjectiveEpisodeStore の FIFO eviction (#117 / 長走対策)。

put が max_episodes_per_player を超えたら occurred_at 昇順で最古から evict
されることを確認する。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.contracts.episodic_memory import (
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    EpisodicCue,
    EpisodicCueSource,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)


def _episode(pid: int, eid: str, occurred_at: datetime, cue_value: str) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=eid,
        player_id=pid,
        occurred_at=occurred_at,
        game_time_label=None,
        source=EpisodeSource(event_ids=(f"evt-{eid}",)),
        location=EpisodeLocation(),
        action=EpisodeAction(tool_name="t"),
        who=("p",),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(
            EpisodicCue(
                axis="topic", value=cue_value,
                source=EpisodicCueSource.OBSERVATION_FREETEXT,
            ),
        ),
        recall_text="...",
    )


class TestFifoEviction:
    """上限を超えた put で最古の episode が消える。"""

    def test_上限を超えた_put_で_最古の_episode_が消える(self) -> None:
        store = InMemorySubjectiveEpisodeStore(max_episodes_per_player=3)
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        store.put(_episode(1, "e1", t0, "a"))
        store.put(_episode(1, "e2", t0 + timedelta(minutes=1), "b"))
        store.put(_episode(1, "e3", t0 + timedelta(minutes=2), "c"))
        store.put(_episode(1, "e4", t0 + timedelta(minutes=3), "d"))

        assert store.get(1, "e1") is None
        assert store.get(1, "e2") is not None
        assert store.get(1, "e4") is not None

    def test_evict_された_episode_の_cue_も_index_から消える(self) -> None:
        store = InMemorySubjectiveEpisodeStore(max_episodes_per_player=2)
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        store.put(_episode(1, "e1", t0, "topic_a"))
        store.put(_episode(1, "e2", t0 + timedelta(minutes=1), "topic_b"))
        store.put(_episode(1, "e3", t0 + timedelta(minutes=2), "topic_c"))

        results = store.list_by_cue(
            1,
            EpisodicCue(
                axis="topic", value="topic_a",
                source=EpisodicCueSource.OBSERVATION_FREETEXT,
            ),
            limit=10,
        )
        assert results == []

    def test_他のプレイヤーの_episode_は_evict_に巻き込まれない(self) -> None:
        store = InMemorySubjectiveEpisodeStore(max_episodes_per_player=2)
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        store.put(_episode(1, "p1_e1", t0, "a"))
        store.put(_episode(1, "p1_e2", t0 + timedelta(minutes=1), "b"))
        store.put(_episode(2, "p2_e1", t0, "a"))
        store.put(_episode(1, "p1_e3", t0 + timedelta(minutes=2), "c"))

        assert store.get(1, "p1_e1") is None
        assert store.get(2, "p2_e1") is not None
