"""Phase 3 Step 3e-2: SubjectiveEpisode caller の dual-path テスト。

主要 caller (Coordinator / ChunkCoordinator scheduler / LinkApplication
Service / Explore tool / PassiveRecall / Reinterp / Promotion) が
``*_by_being`` 経路で episode を読み書きすることを確認する。
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import EpisodicChunkCoordinator
from ai_rpg_world.application.llm.services.episodic_subjective_completion_schedulers import (
    InlineEpisodicSubjectiveScheduler,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode

_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)

def _ep(episode_id: str='e1', player_id: int=1) -> SubjectiveEpisode:
    cue = EpisodicCue(axis='place_spot', value='1', source=EpisodicCueSource.RUNTIME_CONTEXT)
    return SubjectiveEpisode(episode_id=episode_id, player_id=player_id, being_id=BeingId(f'being_w1_p{player_id}'), occurred_at=_NOW, game_time_label='12:00', source=EpisodeSource(event_ids=('evt',)), location=EpisodeLocation(spot_id=1), action=EpisodeAction(tool_name='x'), who=(), what='w', why=None, observed='o', expected=None, outcome='ok', prediction_error=None, felt=None, interpreted='i', cues=(cue,), recall_text='r', recall_count=0, last_recalled_at=None)

class TestChunkCoordinatorPutEpisodeDualPath:
    """``EpisodicChunkCoordinator._put_episode`` の dispatch 動作。"""

    def test_put_episode_uses_episode_being_id(self) -> None:
        """_put_episode は episode.being_id で by being 経路。"""
        store = MagicMock()
        builder = MagicMock()
        builder._episodic_episode_store = store
        ep = _ep(player_id=7)
        EpisodicChunkCoordinator._put_episode(builder, ep)
        store.put_by_being.assert_called_once_with(ep.being_id, ep)
        store.put.assert_not_called()

class TestInlineSchedulerPutDualPath:
    """``InlineEpisodicSubjectiveScheduler._put_episode`` の dispatch 動作。"""

    def test_put_episode_uses_episode_being_id(self) -> None:
        """_put_episode は episode.being_id で by being 経路。"""
        scheduler = MagicMock()
        store = MagicMock()
        scheduler._store = store
        ep = _ep(player_id=3)
        InlineEpisodicSubjectiveScheduler._put_episode(scheduler, ep)
        store.put_by_being.assert_called_once_with(ep.being_id, ep)
