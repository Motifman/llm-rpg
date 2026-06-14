"""Phase 3 Step 3e-2: SubjectiveEpisode caller の dual-path テスト。

主要 caller (Coordinator / ChunkCoordinator scheduler / LinkApplication
Service / Explore tool / PassiveRecall / Reinterp / Promotion) が
Resolver 注入時に ``*_by_being`` 経路で episode を読み書きすることを確認する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)
from ai_rpg_world.application.llm.services.episodic_subjective_completion_schedulers import (
    InlineEpisodicSubjectiveScheduler,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from tests.application.llm._reinterpretation_being_test_helpers import (
    make_reinterpretation_being_setup,
)


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _ep(episode_id: str = "e1", player_id: int = 1) -> SubjectiveEpisode:
    cue = EpisodicCue(
        axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT
    )
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=_NOW,
        game_time_label="12:00",
        source=EpisodeSource(event_ids=("evt",)),
        location=EpisodeLocation(spot_id=1),
        action=EpisodeAction(tool_name="x"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted="i",
        cues=(cue,),
        recall_text="r",
        recall_count=0,
        last_recalled_at=None,
    )


class TestChunkCoordinatorPutEpisodeDualPath:
    """``EpisodicChunkCoordinator._put_episode`` の dispatch 動作。"""

    def test_being_id_注入時は_by_being_経路(self) -> None:
        store = MagicMock()
        # _put_episode の helper を直接たたく (構築コスト回避)
        builder = MagicMock()
        builder._episodic_episode_store = store
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        resolver = MagicMock()
        being_id = MagicMock(name="BeingId")
        resolver.resolve_being_id = MagicMock(return_value=being_id)
        builder._being_attachment_resolver = resolver
        from ai_rpg_world.domain.world.value_object.world_id import WorldId

        builder._default_world_id = WorldId(1)
        ep = _ep(player_id=7)
        EpisodicChunkCoordinator._put_episode(builder, ep)
        store.put_by_being.assert_called_once_with(being_id, ep)
        store.put.assert_not_called()

    def test_resolver_未注入時は_legacy_put(self) -> None:
        store = MagicMock()
        builder = MagicMock()
        builder._episodic_episode_store = store
        builder._being_attachment_resolver = None
        builder._default_world_id = None
        ep = _ep()
        EpisodicChunkCoordinator._put_episode(builder, ep)
        store.put.assert_called_once_with(ep)
        store.put_by_being.assert_not_called()


class TestInlineSchedulerPutDualPath:
    """``InlineEpisodicSubjectiveScheduler._put_episode`` の dispatch 動作。"""

    def test_being_id_注入時は_by_being_経路(self) -> None:
        scheduler = MagicMock()
        store = MagicMock()
        scheduler._store = store
        resolver = MagicMock()
        being_id = MagicMock(name="BeingId")
        resolver.resolve_being_id = MagicMock(return_value=being_id)
        scheduler._being_attachment_resolver = resolver
        from ai_rpg_world.domain.world.value_object.world_id import WorldId

        scheduler._default_world_id = WorldId(1)
        ep = _ep(player_id=3)
        InlineEpisodicSubjectiveScheduler._put_episode(scheduler, ep)
        store.put_by_being.assert_called_once_with(being_id, ep)

    def test_resolver_未注入時は_legacy_put(self) -> None:
        scheduler = MagicMock()
        store = MagicMock()
        scheduler._store = store
        scheduler._being_attachment_resolver = None
        scheduler._default_world_id = None
        ep = _ep()
        InlineEpisodicSubjectiveScheduler._put_episode(scheduler, ep)
        store.put.assert_called_once_with(ep)
        store.put_by_being.assert_not_called()


class TestReinterpretationCoordinatorEpisodeLookupByBeing:
    """``EpisodicReinterpretationCoordinator._build_episode_items`` の
    episode lookup が being_id 経路で行われる。"""

    def test_lookup_は_being_id_経路_(self) -> None:
        from ai_rpg_world.application.llm.services.episodic_reinterpretation_coordinator import (
            EpisodicReinterpretationCoordinator,
        )
        from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
            EpisodicRecallObservation,
        )

        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_reinterpretation_being_setup()
        being_id = setup.provision(1)
        ep = _ep("ep-1")
        # 必ず being_id 経路で書く
        episodes.put_by_being(being_id, ep)
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=setup.recall_buffer,
            journal_store=setup.journal,
            completion=None,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        obs = EpisodicRecallObservation(
            recall_id="r1",
            player_id=1,
            episode_id="ep-1",
            recalled_at=_NOW,
            source_axes=("temporal",),
            current_state_snapshot="s",
            recent_events_snapshot="r",
            persona_snapshot="p",
            situation_cues=(),
            turn_index=0,
        )
        # private API を直接呼んで検証 (build_episode_items に being_id を渡す)
        items = coord._build_episode_items(1, (obs,), being_id=being_id)
        assert len(items) == 1
        assert items[0].episode.episode_id == "ep-1"
