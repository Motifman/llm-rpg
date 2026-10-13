"""想起後再解釈の buffer / journal の検証。coordinator は #1631 で消した。"""
from __future__ import annotations

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_id import BeingId as _MIG_BeingId

being_id = _MIG_BeingId('being_w1_p1')
from datetime import datetime, timedelta, timezone

from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
    InMemoryEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import EpisodicRecallObservation
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode


def _episode(*, episode_id: str, player_id: int=7, being_id: BeingId | None=None, recall_text: str='初期の一人称回想。') -> SubjectiveEpisode:
    bid = being_id if being_id is not None else BeingId(f'being_w1_p{player_id}')
    return SubjectiveEpisode(episode_id=episode_id, player_id=player_id, being_id=bid, occurred_at=datetime(2026, 5, 4, 1, 0, tzinfo=timezone.utc), game_time_label=None, source=EpisodeSource(event_ids=('evt-a',)), location=EpisodeLocation(spot_id=10), action=EpisodeAction(tool_name='world_no_op'), who=('player:self',), what='古い扉を調べた', why=None, observed='古い扉は固く閉ざされていた。', expected=None, outcome='未解決', prediction_error=None, felt='caution', interpreted='閉ざされた場所だと思った。', cues=(EpisodicCue(axis='place_spot', value='10', source=EpisodicCueSource.RUNTIME_CONTEXT),), recall_text=recall_text)

def _recall(*, recall_id: str, episode_id: str, at: datetime, turn_index: int, player_id: int=7) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(recall_id=recall_id, player_id=player_id, episode_id=episode_id, recalled_at=at, source_axes=('temporal',), current_state_snapshot='現在地: 古い廊下', recent_events_snapshot='扉の前で立ち止まった。', persona_snapshot='一人称: 私', situation_cues=('place_spot:10',), turn_index=turn_index)
_BEING_7 = BeingId('being_w1_p7')

class TestInMemoryEpisodicRecallBufferStore:
    """想起 observation を episode 単位で束ねる。"""

    def test_peek_batch_deduplicates_episode_and_caps_contexts(self) -> None:
        """同じ episode の想起は 1 episode として数え、contexts は上限で切る。"""
        base = datetime(2026, 5, 4, tzinfo=timezone.utc)
        store = InMemoryEpisodicRecallBufferStore()
        for i in range(5):
            store.append_by_being(_BEING_7, _recall(recall_id=f'r{i}', episode_id='ep-a', at=base + timedelta(minutes=i), turn_index=i))
        store.append_by_being(_BEING_7, _recall(recall_id='r-b', episode_id='ep-b', at=base + timedelta(minutes=10), turn_index=10))
        batch = store.peek_batch_by_being(_BEING_7, batch_size=1, max_contexts_per_episode=3)
        assert [r.recall_id for r in batch] == ['r0', 'r1', 'r2']
        assert store.pending_count_by_being(_BEING_7) == 6

class TestInMemoryEpisodicReinterpretationJournalStore:
    """active entry だけが通常参照に残る。"""

    def test_put_active_supersedes_previous_active_entry(self) -> None:
        """新 active 保存時に旧 active は superseded となり get_active から外れる。"""
        store = InMemoryEpisodicReinterpretationJournalStore()
        t0 = datetime(2026, 5, 4, tzinfo=timezone.utc)
        first = EpisodicReinterpretationEntry(entry_id='j1', player_id=7, being_id=_BEING_7, episode_id='ep-a', created_at=t0, turn_index=1, current_interpretation='古い意味。', current_recall_text='古い回想。', source_recall_ids=('r1',))
        second = EpisodicReinterpretationEntry(entry_id='j2', player_id=7, being_id=_BEING_7, episode_id='ep-a', created_at=t0 + timedelta(minutes=1), turn_index=2, current_interpretation='新しい意味。', current_recall_text='新しい回想。', source_recall_ids=('r2',))
        store.put_active_by_being(_BEING_7, first)
        store.put_active_by_being(_BEING_7, second)
        assert store.get_active_by_being(_BEING_7, 'ep-a') == second
        history = store.list_by_episode_by_being(_BEING_7, 'ep-a')
        assert [e.entry_id for e in history] == ['j2', 'j1']
        assert history[1].status.value == 'superseded'
