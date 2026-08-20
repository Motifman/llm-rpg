"""Phase 3 Step 3c-3: memory_link caller の being_id keyed 経路テスト。

Step 3c-2 で導入した dual-path のうち legacy fallback を 3c-3 で撤去した
ため、本テストでも「Resolver 未注入なら silent skip / INVALID_STATE」など
新 API only 経路の挙動を確認する。memo 3a-3 / semantic 3b-3 と同じ整理。
"""
from __future__ import annotations
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_id import BeingId as _MIG_BeingId
being_id = _MIG_BeingId('being_w1_p1')
import json
from datetime import datetime, timezone
import pytest
from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import EpisodicMemoryLinkApplicationService
from ai_rpg_world.application.llm.services.afterglow_store import AfterglowEntry, AfterglowSource, InMemoryAfterglowStore, make_afterglow_handle
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import EpisodicPassiveRecallRetrievalService
from ai_rpg_world.application.llm.services.episodic_recall_slot_store import InMemoryEpisodicRecallSlotStore, RecallSlotEntry
from ai_rpg_world.application.llm.services.episodic_spreading_activation import neighbor_priming_scores
from ai_rpg_world.application.llm.services.executors.episodic_memory_explore_tool_executor import EpisodicMemoryExploreToolExecutor
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import InMemorySubjectiveEpisodeStore
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_MEMORY_EXPLORE_RELATED
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import MemoryLink, MemoryLinkType
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from tests.application.llm._memory_link_being_test_helpers import make_memory_link_being_setup
_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)

def _ep(*, episode_id: str, player_id: int=1, occurred_at: datetime=_NOW) -> SubjectiveEpisode:
    cue = EpisodicCue(axis='place_spot', value='1', source=EpisodicCueSource.RUNTIME_CONTEXT)
    return SubjectiveEpisode(episode_id=episode_id, player_id=player_id, being_id=BeingId(f'being_w1_p{player_id}'), occurred_at=occurred_at, game_time_label='12:00', source=EpisodeSource(event_ids=('e1',)), location=EpisodeLocation(spot_id=1), action=EpisodeAction(tool_name='x'), who=(), what='w', why=None, observed='o', expected=None, outcome='ok', prediction_error=None, felt=None, interpreted='解釈', cues=(cue,), recall_text=f'r-{episode_id}', recall_count=4)

def _link(*, a: str, b: str, player_id: int=1, strength: float=0.9) -> MemoryLink:
    (na, nb) = sorted((a, b))
    return MemoryLink(link_id=f'l-{na}-{nb}', player_id=player_id, episode_id_a=na, episode_id_b=nb, link_type=MemoryLinkType.CO_RECALL, strength=strength, co_activation_count=1, created_at=_NOW, last_activated_at=_NOW, decay_rate=0.001)

class TestEpisodicMemoryLinkApplicationServiceCallerBeingId:
    """``EpisodicMemoryLinkApplicationService`` が呼び出し側の being_id で
    link を書く。"""

    def test_creates_episode_committed_being_id_link(self) -> None:
        """on episode committed は being id 経路で link を作る。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        svc = EpisodicMemoryLinkApplicationService(episodes, setup.link_store)
        from datetime import timedelta as _td
        prev = _ep(episode_id='prev', occurred_at=_NOW - _td(minutes=5))
        newest = _ep(episode_id='newest', occurred_at=_NOW)
        episodes.put_by_being(being_id, prev)
        episodes.put_by_being(being_id, newest)
        svc.on_episode_committed(newest, being_id, now=_NOW)
        assert len(setup.link_store.list_all_links_for_being(being_id)) == 1

    def test_caller_being_id_required_for_link(self) -> None:
        """呼び出し側が being_id を渡さないと link は作られない (TypeError)。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        svc = EpisodicMemoryLinkApplicationService(episodes, setup.link_store)
        from datetime import timedelta as _td
        prev = _ep(episode_id='prev', occurred_at=_NOW - _td(minutes=5))
        newest = _ep(episode_id='newest', occurred_at=_NOW)
        episodes.put_by_being(being_id, prev)
        episodes.put_by_being(being_id, newest)
        with pytest.raises(TypeError):
            svc.on_episode_committed(newest, now=_NOW)

class TestEpisodicMemoryExploreToolExecutorActingBeingPath:
    """``EpisodicMemoryExploreToolExecutor`` が ``ActingBeing`` 経路で link を引く。"""

    def test_afterglow_and_slot_missing_invalid_state(self) -> None:
        """afterglow_store も slot_store も無いと handle 解決不能で INVALID_STATE。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        setup.provision(1)
        acting = setup.acting_for(1)
        episodes.put_by_being(acting.being_id, _ep(episode_id='seed'))
        svc = EpisodicMemoryLinkApplicationService(episodes, setup.link_store)
        executor = EpisodicMemoryExploreToolExecutor(episode_store=episodes, link_store=setup.link_store, link_service=svc)
        handlers = executor.get_handlers()
        result = handlers[TOOL_NAME_MEMORY_EXPLORE_RELATED](acting, {'handle': make_afterglow_handle('seed'), 'top_k': 5})
        assert result.success is False
        assert result.error_code == 'INVALID_STATE'

    def test_being_id_via_link_explore(self) -> None:
        """prompt に出る handle で、同じ episode を起点に関連記憶を辿れる。"""
        episodes = InMemorySubjectiveEpisodeStore()
        afterglow_store = InMemoryAfterglowStore()
        slot_store = InMemoryEpisodicRecallSlotStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        acting = setup.acting_for(1)
        episodes.put_by_being(being_id, _ep(episode_id='seed'))
        episodes.put_by_being(being_id, _ep(episode_id='other'))
        afterglow_store.apply_decision(being_id, (AfterglowEntry(episode_id='seed', heading='種になった記憶', entered_tick=1, source=AfterglowSource.WEAK_RECALL),))
        setup.link_store.upsert_link_by_being(being_id, _link(a='seed', b='other', strength=0.9))
        svc = EpisodicMemoryLinkApplicationService(episodes, setup.link_store)
        executor = EpisodicMemoryExploreToolExecutor(episode_store=episodes, link_store=setup.link_store, link_service=svc, afterglow_store=afterglow_store, slot_store=slot_store)
        handlers = executor.get_handlers()
        result = handlers[TOOL_NAME_MEMORY_EXPLORE_RELATED](acting, {'handle': make_afterglow_handle('seed'), 'top_k': 5})
        assert result.success is True
        payload = json.loads(result.message)
        ids = [r['episode_id'] for r in payload['related_episodes']]
        assert 'other' in ids

    def test_handle_consumed_by_recall_by_handle_can_still_explore_from_slot(self) -> None:
        """本文を読んで afterglow から消えた handle でも、recall slot 経由で関連記憶を辿れる。"""
        episodes = InMemorySubjectiveEpisodeStore()
        afterglow_store = InMemoryAfterglowStore()
        slot_store = InMemoryEpisodicRecallSlotStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        acting = setup.acting_for(1)
        episodes.put_by_being(being_id, _ep(episode_id='seed'))
        episodes.put_by_being(being_id, _ep(episode_id='other'))
        afterglow_store.apply_decision(being_id, (AfterglowEntry(episode_id='seed', heading='種になった記憶', entered_tick=1, source=AfterglowSource.WEAK_RECALL),))
        afterglow_store.remove(being_id, 'seed')
        slot_store.force_insert(being_id, RecallSlotEntry(episode_id='seed', entered_tick=2), capacity=4)
        setup.link_store.upsert_link_by_being(being_id, _link(a='seed', b='other', strength=0.9))
        svc = EpisodicMemoryLinkApplicationService(episodes, setup.link_store)
        executor = EpisodicMemoryExploreToolExecutor(episode_store=episodes, link_store=setup.link_store, link_service=svc, afterglow_store=afterglow_store, slot_store=slot_store)
        result = executor.get_handlers()[TOOL_NAME_MEMORY_EXPLORE_RELATED](acting, {'handle': make_afterglow_handle('seed'), 'top_k': 5})
        assert result.success is True
        payload = json.loads(result.message)
        ids = [r['episode_id'] for r in payload['related_episodes']]
        assert 'other' in ids

    def test_unknown_handle_returns_available_handles(self) -> None:
        """存在しない handle は SYSTEM_ERROR ではなく、有効な handle 一覧付きで失敗する。"""
        episodes = InMemorySubjectiveEpisodeStore()
        afterglow_store = InMemoryAfterglowStore()
        slot_store = InMemoryEpisodicRecallSlotStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        acting = setup.acting_for(1)
        afterglow_store.apply_decision(being_id, (AfterglowEntry(episode_id='seed', heading='種になった記憶', entered_tick=1, source=AfterglowSource.WEAK_RECALL),))
        svc = EpisodicMemoryLinkApplicationService(episodes, setup.link_store)
        executor = EpisodicMemoryExploreToolExecutor(episode_store=episodes, link_store=setup.link_store, link_service=svc, afterglow_store=afterglow_store, slot_store=slot_store)
        handlers = executor.get_handlers()
        result = handlers[TOOL_NAME_MEMORY_EXPLORE_RELATED](acting, {'handle': 'ep_missing', 'top_k': 5})
        assert result.success is False
        assert result.error_code == 'INVALID_ARGUMENT'
        assert '有効な handle' in result.message
        assert make_afterglow_handle('seed') in result.message
        assert 'SYSTEM_ERROR' not in (result.error_code or '')

class TestEpisodicPassiveRecallRetrievalServiceDualPath:
    """``EpisodicPassiveRecallRetrievalService`` の spreading activation が
    being_id 経路で link を引く。"""

    def test_resolver_uninjected_all_skip_completes(self) -> None:
        """Phase 3 Step 3e-3: episode_store も legacy 撤去後、Resolver 未注入時は
        temporal/cue/spreading すべての軸が空になる graceful fallback。turn は
        止まらず、prompt 強化が完全に痩せるだけ。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        svc = EpisodicPassiveRecallRetrievalService(episodes, link_store=setup.link_store)
        result = svc.retrieve(being_id=being_id, situation_cues=(), limit_per_axis=5, max_candidates=10, now=_NOW)
        ids = {c.episode.episode_id for c in result.candidates}
        assert ids == set()

    def test_being_id_spreading_being_id_works(self) -> None:
        """being id 注入時は spreading が being id 経路で 動く。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        seed_ep = _ep(episode_id='seed')
        far_ep = _ep(episode_id='far')
        episodes.put_by_being(being_id, seed_ep)
        episodes.put_by_being(being_id, far_ep)
        setup.link_store.upsert_link_by_being(being_id, _link(a='seed', b='far', strength=0.9))
        svc = EpisodicPassiveRecallRetrievalService(episodes, link_store=setup.link_store)
        result = svc.retrieve(being_id=being_id, situation_cues=(), limit_per_axis=5, max_candidates=10, now=_NOW)
        ids = {c.episode.episode_id for c in result.candidates}
        assert 'seed' in ids
        assert 'far' in ids

class TestEpisodicSemanticClusterPromotionServiceMemoryLinkPath:
    """``EpisodicSemanticClusterPromotionService.on_after_tool_turn`` の link 走査が
    being_id keyed only で動くことを確認する。"""

    def test_caller_being_id_drives_link_scan(self) -> None:
        """呼び出し側の being_id で link 走査と semantic 書き込みが行われる。"""
        from tests.application.llm._semantic_being_test_helpers import make_semantic_being_setup
        from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import EpisodicSemanticClusterPromotionService
        episodes = InMemorySubjectiveEpisodeStore()
        link_store = make_memory_link_being_setup().link_store
        sem_setup = make_semantic_being_setup()
        being_id = sem_setup.provision(1)
        for (i, eid) in enumerate(['x', 'y', 'z']):
            from dataclasses import replace as _replace
            base = _ep(episode_id=eid)
            episodes.put_by_being(being_id, _replace(base, interpreted=f'主観文{i}'))
        link_store.upsert_link_by_being(being_id, _link(a='x', b='y'))
        link_store.upsert_link_by_being(being_id, _link(a='y', b='z'))
        link_store.upsert_link_by_being(being_id, _link(a='x', b='z'))
        promo = EpisodicSemanticClusterPromotionService(episode_store=episodes, link_store=link_store, semantic_store=sem_setup.semantic_store, promotion_frontier=None)
        promo.on_after_tool_turn(1, being_id, now=_NOW)
        assert len(sem_setup.list_entries(1)) == 1

class TestSpreadingActivationBeingIdParam:
    """``neighbor_priming_scores`` は being_id 必須 (Phase 3 Step 3c-3)。"""

    def test_being_id_being_id_link(self) -> None:
        """beingid を渡すと beingid 経路で link をたどる。"""
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        setup.link_store.upsert_link_by_being(being_id, _link(a='seed', b='other', strength=0.9))
        result = neighbor_priming_scores(being_id=being_id, seed_episode_ids=frozenset({'seed'}), link_store=setup.link_store, now=_NOW, max_hops=2)
        assert 'other' in result

    def test_being_id_raises_type_error(self) -> None:
        """Phase 3 Step 3c-3: being_id は BeingId 型必須。"""
        setup = make_memory_link_being_setup()
        with pytest.raises(TypeError, match='being_id'):
            neighbor_priming_scores(being_id='not-a-being-id', seed_episode_ids=frozenset({'seed'}), link_store=setup.link_store, now=_NOW, max_hops=2)
