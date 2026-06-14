"""InMemorySubjectiveEpisodeStore の FIFO eviction (#117 / 長走対策)。

put が max_episodes_per_player を超えたら occurred_at 昇順で最古から evict
されることを確認する。
"""

from __future__ import annotations

# Phase 3 Step 3e-3 bulk migration: episode_store の player_id 経路撤去に
# 伴い、本ファイルの ``being_id`` 参照を deterministic な ``BeingId`` の
# 既定値で受ける (= テスト内で異なる player_id を使う箇所は個別に上書き)。
# BeingProvisioningService は ``being_w<world>_p<player>`` 形式を使う。
from ai_rpg_world.domain.being.value_object.being_id import (
    BeingId as _MIG_BeingId,
)

being_id = _MIG_BeingId("being_w1_p1")

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
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
        store.put_by_being(being_id, _episode(1, "e1", t0, "a"))
        store.put_by_being(being_id, _episode(1, "e2", t0 + timedelta(minutes=1), "b"))
        store.put_by_being(being_id, _episode(1, "e3", t0 + timedelta(minutes=2), "c"))
        store.put_by_being(being_id, _episode(1, "e4", t0 + timedelta(minutes=3), "d"))

        assert store.get_by_being(being_id, "e1") is None
        assert store.get_by_being(being_id, "e2") is not None
        assert store.get_by_being(being_id, "e4") is not None

    def test_evict_された_episode_の_cue_も_index_から消える(self) -> None:
        store = InMemorySubjectiveEpisodeStore(max_episodes_per_player=2)
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        store.put_by_being(being_id, _episode(1, "e1", t0, "topic_a"))
        store.put_by_being(being_id, _episode(1, "e2", t0 + timedelta(minutes=1), "topic_b"))
        store.put_by_being(being_id, _episode(1, "e3", t0 + timedelta(minutes=2), "topic_c"))

        results = store.list_by_cue_by_being(being_id,
            EpisodicCue(
                axis="topic", value="topic_a",
                source=EpisodicCueSource.OBSERVATION_FREETEXT,
            ),
            limit=10,
        )
        assert results == []

    def test_他の_Being_の_episode_は_evict_に巻き込まれない(self) -> None:
        """Phase 3 Step 3e-3: cap は Being 単位。別 Being の episode は影響を受けない。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId as _BID

        being_p1 = _BID("being_w1_p1")
        being_p2 = _BID("being_w1_p2")
        store = InMemorySubjectiveEpisodeStore(max_episodes_per_player=2)
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        store.put_by_being(being_p1, _episode(1, "p1_e1", t0, "a"))
        store.put_by_being(being_p1, _episode(1, "p1_e2", t0 + timedelta(minutes=1), "b"))
        store.put_by_being(being_p2, _episode(2, "p2_e1", t0, "a"))
        store.put_by_being(being_p1, _episode(1, "p1_e3", t0 + timedelta(minutes=2), "c"))

        # p1 は cap=2 で oldest が evict
        assert store.get_by_being(being_p1, "p1_e1") is None
        # p2 は別 Being なので影響なし
        assert store.get_by_being(being_p2, "p2_e1") is not None
