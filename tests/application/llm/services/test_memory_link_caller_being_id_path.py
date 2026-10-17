"""Phase 3 Step 3c-3: memory_link caller の being_id keyed 経路テスト。

Step 3c-2 で導入した dual-path のうち legacy fallback を 3c-3 で撤去した
ため、本テストでも「Resolver 未注入なら silent skip / INVALID_STATE」など
新 API only 経路の挙動を確認する。memo 3a-3 / semantic 3b-3 と同じ整理。
"""
from __future__ import annotations

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_id import BeingId as _MIG_BeingId

being_id = _MIG_BeingId('being_w1_p1')
from datetime import datetime, timezone

from tests.application.llm._memory_link_being_test_helpers import make_memory_link_being_setup

from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import InMemorySubjectiveEpisodeStore
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import MemoryLink, MemoryLinkType
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode

_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)

def _ep(*, episode_id: str, player_id: int=1, occurred_at: datetime=_NOW) -> SubjectiveEpisode:
    cue = EpisodicCue(axis='place_spot', value='1', source=EpisodicCueSource.RUNTIME_CONTEXT)
    return SubjectiveEpisode(episode_id=episode_id, player_id=player_id, being_id=BeingId(f'being_w1_p{player_id}'), occurred_at=occurred_at, game_time_label='12:00', source=EpisodeSource(event_ids=('e1',)), location=EpisodeLocation(spot_id=1), action=EpisodeAction(tool_name='x'), who=(), what='w', why=None, observed='o', expected=None, outcome='ok', prediction_error=None, felt=None, interpreted='解釈', cues=(cue,), recall_text=f'r-{episode_id}', recall_count=4)

def _link(*, a: str, b: str, player_id: int=1, strength: float=0.9, being_id: BeingId | None=None) -> MemoryLink:
    (na, nb) = sorted((a, b))
    resolved_being_id = being_id or BeingId(f'being_w1_p{player_id}')
    return MemoryLink(link_id=f'l-{na}-{nb}', player_id=player_id, being_id=resolved_being_id, episode_id_a=na, episode_id_b=nb, link_type=MemoryLinkType.CO_RECALL, strength=strength, co_activation_count=1, created_at=_NOW, last_activated_at=_NOW, decay_rate=0.001)

class TestEpisodicMemoryLinkApplicationServiceCallerBeingId:
    """``EpisodicMemoryLinkApplicationService`` が呼び出し側の being_id で
    link を書く。"""

    def test_episode_being_id_drives_temporal_link(self) -> None:
        """on_episode_committed(episode) は episode.being_id の store に TEMPORAL リンクを書く。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        svc = EpisodicMemoryLinkApplicationService(episodes, setup.link_store)
        from datetime import timedelta as _td
        prev = _ep(episode_id='prev', occurred_at=_NOW - _td(minutes=5))
        newest = _ep(episode_id='newest', occurred_at=_NOW)
        episodes.put_by_being(being_id, prev)
        episodes.put_by_being(being_id, newest)
        svc.on_episode_committed(newest, now=_NOW)
        assert len(setup.link_store.list_all_links_for_being(being_id)) == 1

    def test_episode_being_id_does_not_write_to_other_being_store(self) -> None:
        """episode.being_id と異なる Being の store には TEMPORAL リンクを書かない。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        other_being_id = BeingId('being_w1_p99')
        svc = EpisodicMemoryLinkApplicationService(episodes, setup.link_store)
        from datetime import timedelta as _td
        prev = _ep(episode_id='prev', occurred_at=_NOW - _td(minutes=5))
        newest = _ep(episode_id='newest', occurred_at=_NOW)
        episodes.put_by_being(being_id, prev)
        episodes.put_by_being(being_id, newest)
        svc.on_episode_committed(newest, now=_NOW)
        assert len(setup.link_store.list_all_links_for_being(being_id)) == 1
        assert len(setup.link_store.list_all_links_for_being(other_being_id)) == 0
