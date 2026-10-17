"""エピソードリンクストアと時間的近接リンクのユニット検証。"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from tests.application.llm._memory_link_being_test_helpers import make_memory_link_being_setup

from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import InMemorySubjectiveEpisodeStore
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import MemoryLink, MemoryLinkType
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode


def _ep(*, episode_id: str, player_id: int, recall_count: int=0, interpreted: str | None='解釈') -> SubjectiveEpisode:
    cue = EpisodicCue(axis='place_spot', value='1', source=EpisodicCueSource.RUNTIME_CONTEXT)
    return SubjectiveEpisode(episode_id=episode_id, player_id=player_id, being_id=BeingId(f'being_w1_p{player_id}'), occurred_at=datetime.now(timezone.utc), game_time_label='12:00', source=EpisodeSource(event_ids=('e1',)), location=EpisodeLocation(spot_id=1), action=EpisodeAction(tool_name='world_no_op'), who=('self',), what='w', why=None, observed='o', expected=None, outcome='ok', prediction_error=None, felt=None, interpreted=interpreted, cues=(cue,), recall_text='r', recall_count=recall_count, last_recalled_at=None)

def test_temporal_link_created_between_recent_pair() -> None:
    """link 書き込みは episode.being_id keyed。"""
    store = InMemorySubjectiveEpisodeStore()
    setup = make_memory_link_being_setup()
    being_id = setup.provision(7)
    svc = EpisodicMemoryLinkApplicationService(store, setup.link_store)
    first = _ep(episode_id='e1', player_id=7)
    second = _ep(episode_id='e2', player_id=7)
    store.put_by_being(being_id, first)
    store.put_by_being(being_id, second)
    svc.on_episode_committed(second)
    assert store.list_recent_by_being(being_id, 2)[0].episode_id == 'e2'
    assert setup.link_store.get_link_by_being(being_id, 'e1', 'e2', MemoryLinkType.TEMPORAL) is not None

def _strong_link(player_id: int, a: str, b: str, *, strength: float=0.9, being_id: BeingId | None=None) -> MemoryLink:
    now = datetime.now(timezone.utc)
    (na, nb) = (a, b) if a < b else (b, a)
    resolved_being_id = being_id or BeingId(f'being_w1_p{player_id}')
    return MemoryLink(link_id=f'memlink-{uuid4().hex}', player_id=player_id, being_id=resolved_being_id, episode_id_a=na, episode_id_b=nb, link_type=MemoryLinkType.CO_RECALL, strength=strength, co_activation_count=1, created_at=now, last_activated_at=now, decay_rate=0.001)

def test_link_store_lists_all_for_being() -> None:
    setup = make_memory_link_being_setup()
    being_id = setup.provision(3)
    setup.link_store.upsert_link_by_being(being_id, _strong_link(3, 'a', 'b'))
    assert len(setup.link_store.list_all_links_for_being(being_id)) == 1
