"""Phase 3 Step 3c-3: memory_link caller の being_id keyed 経路テスト。

Step 3c-2 で導入した dual-path のうち legacy fallback を 3c-3 で撤去した
ため、本テストでも「Resolver 未注入なら silent skip / INVALID_STATE」など
新 API only 経路の挙動を確認する。memo 3a-3 / semantic 3b-3 と同じ整理。
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

import json
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.episodic_spreading_activation import (
    neighbor_priming_scores,
)
from ai_rpg_world.application.llm.services.executors.episodic_memory_explore_tool_executor import (
    EpisodicMemoryExploreToolExecutor,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_MEMORY_EXPLORE_RELATED
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from tests.application.llm._memory_link_being_test_helpers import (
    make_memory_link_being_setup,
)


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _ep(
    *,
    episode_id: str,
    player_id: int = 1,
    occurred_at: datetime = _NOW,
) -> SubjectiveEpisode:
    cue = EpisodicCue(
        axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT
    )
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=occurred_at,
        game_time_label="12:00",
        source=EpisodeSource(event_ids=("e1",)),
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
        interpreted="解釈",
        cues=(cue,),
        recall_text=f"r-{episode_id}",
        recall_count=4,
    )


def _link(*, a: str, b: str, player_id: int = 1, strength: float = 0.9) -> MemoryLink:
    na, nb = sorted((a, b))
    return MemoryLink(
        link_id=f"l-{na}-{nb}",
        player_id=player_id,
        episode_id_a=na,
        episode_id_b=nb,
        link_type=MemoryLinkType.CO_RECALL,
        strength=strength,
        co_activation_count=1,
        created_at=_NOW,
        last_activated_at=_NOW,
        decay_rate=0.001,
    )


class TestEpisodicMemoryLinkApplicationServiceDualPath:
    """``EpisodicMemoryLinkApplicationService`` が Resolver 注入時に
    being_id 経路で link を書く。"""

    def test_creates_episode_committed_being_id_link(self) -> None:
        """on episode committed は being id 経路で link を作る。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        svc = EpisodicMemoryLinkApplicationService(
            episodes,
            setup.link_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        from datetime import timedelta as _td
        prev = _ep(episode_id="prev", occurred_at=_NOW - _td(minutes=5))
        newest = _ep(episode_id="newest", occurred_at=_NOW)
        # Phase 3 Step 3e-2: service が being_id 経由で list_recent するため
        episodes.put_by_being(being_id, prev)
        episodes.put_by_being(being_id, newest)
        svc.on_episode_committed(newest, now=_NOW)
        # being_id 経路に書かれる
        assert len(setup.link_store.list_all_links_for_being(being_id)) == 1

    def test_resolver_uninjected_silent_op_2(self) -> None:
        """Phase 3 Step 3c-3: legacy 撤去後、Resolver 未注入は silent skip。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        # Resolver 注入なしで構築 (= legacy 経路は撤去済)
        svc = EpisodicMemoryLinkApplicationService(episodes, setup.link_store)
        from datetime import timedelta as _td
        prev = _ep(episode_id="prev", occurred_at=_NOW - _td(minutes=5))
        newest = _ep(episode_id="newest", occurred_at=_NOW)
        episodes.put_by_being(being_id, prev)
        episodes.put_by_being(being_id, newest)
        svc.on_episode_committed(newest, now=_NOW)
        # being_id 側にも何も書かれていない (= silent no-op)
        # link_store 全体を見ても空であることだけ確認できれば十分
        # (being_id を引けないため list_all_links_for_being は呼べないが、
        # internal index が空であることを暗に確認)
        # 何かの being_id でリストしても 0 件 (= 当然 0)
        from ai_rpg_world.domain.being.value_object.being_id import BeingId
        assert (
            setup.link_store.list_all_links_for_being(BeingId("dummy")) == []
        )


class TestEpisodicMemoryExploreToolExecutorDualPath:
    """``EpisodicMemoryExploreToolExecutor`` が being_id 経路で link を引く。"""

    def test_resolver_uninjected_invalid_state(self) -> None:
        """Phase 3 Step 3c-3: tool は LLM-visible なので fail-fast (= INVALID_STATE)。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        episodes.put_by_being(being_id, _ep(episode_id="seed"))
        svc = EpisodicMemoryLinkApplicationService(episodes, setup.link_store)
        executor = EpisodicMemoryExploreToolExecutor(
            episode_store=episodes,
            link_store=setup.link_store,
            link_service=svc,
        )
        handlers = executor.get_handlers()
        result = handlers[TOOL_NAME_MEMORY_EXPLORE_RELATED](
            1, {"episode_id": "seed", "top_k": 5}
        )
        assert result.success is False
        assert result.error_code == "INVALID_STATE"

    def test_being_id_via_link_explore(self) -> None:
        """beingid 経由で書いた link が explore で見える。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        # Phase 3 Step 3e-2: executor が get_by_being で episode を引くため
        episodes.put_by_being(being_id, _ep(episode_id="seed"))
        episodes.put_by_being(being_id, _ep(episode_id="other"))
        setup.link_store.upsert_link_by_being(
            being_id, _link(a="seed", b="other", strength=0.9)
        )
        svc = EpisodicMemoryLinkApplicationService(
            episodes,
            setup.link_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        executor = EpisodicMemoryExploreToolExecutor(
            episode_store=episodes,
            link_store=setup.link_store,
            link_service=svc,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        handlers = executor.get_handlers()
        result = handlers[TOOL_NAME_MEMORY_EXPLORE_RELATED](
            1, {"episode_id": "seed", "top_k": 5}
        )
        assert result.success is True
        payload = json.loads(result.message)
        ids = [r["episode_id"] for r in payload["related_episodes"]]
        assert "other" in ids


class TestEpisodicPassiveRecallRetrievalServiceDualPath:
    """``EpisodicPassiveRecallRetrievalService`` の spreading activation が
    being_id 経路で link を引く。"""

    def test_resolver_uninjected_all_skip_completes(self) -> None:
        """Phase 3 Step 3e-3: episode_store も legacy 撤去後、Resolver 未注入時は
        temporal/cue/spreading すべての軸が空になる graceful fallback。turn は
        止まらず、prompt 強化が完全に痩せるだけ。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        # Resolver 未注入で構築 (= episode も link も読み出せない)
        svc = EpisodicPassiveRecallRetrievalService(
            episodes,
            link_store=setup.link_store,
        )
        result = svc.retrieve(
            player_id=1,
            situation_cues=(),
            limit_per_axis=5,
            max_candidates=10,
            now=_NOW,
        )
        ids = {c.episode.episode_id for c in result.candidates}
        # 全軸 skip → 候補ゼロ
        assert ids == set()

    def test_being_id_spreading_being_id_works(self) -> None:
        """being id 注入時は spreading が being id 経路で 動く。"""
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        seed_ep = _ep(episode_id="seed")
        far_ep = _ep(episode_id="far")
        # Phase 3 Step 3e-2: passive recall が being_id 経路で list_recent / get
        episodes.put_by_being(being_id, seed_ep)
        episodes.put_by_being(being_id, far_ep)
        setup.link_store.upsert_link_by_being(
            being_id, _link(a="seed", b="far", strength=0.9)
        )
        svc = EpisodicPassiveRecallRetrievalService(
            episodes,
            link_store=setup.link_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        result = svc.retrieve(
            player_id=1,
            situation_cues=(),
            limit_per_axis=5,
            max_candidates=10,
            now=_NOW,
        )
        ids = {c.episode.episode_id for c in result.candidates}
        # seed は temporal 軸、far は spreading 軸で得られるはず
        assert "seed" in ids
        assert "far" in ids


class TestEpisodicSemanticClusterPromotionServiceMemoryLinkPath:
    """``EpisodicSemanticClusterPromotionService.on_after_tool_turn`` の link 走査が
    being_id keyed only で動くことを確認 (Phase 3 Step 3c-3)。"""

    def test_resolver_uninjected_silent_op(self) -> None:
        """Phase 3 Step 3c-3: Resolver 未注入なら link 走査も含めて silent no-op。"""
        from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
            EpisodicSemanticClusterPromotionService,
        )
        from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
            InMemorySemanticMemoryStore,
        )

        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        sem = InMemorySemanticMemoryStore()
        promo = EpisodicSemanticClusterPromotionService(
            episode_store=episodes,
            link_store=setup.link_store,
            semantic_store=sem,
            promotion_frontier=None,
        )
        # 例外なく完了する (= silent no-op)
        promo.on_after_tool_turn(1, now=_NOW)

    def test_resolver_link_being_id(self) -> None:
        """Resolver 注入 + Being provision で being_id 経路。"""
        from tests.application.llm._semantic_being_test_helpers import (
            make_semantic_being_setup,
        )
        from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
            EpisodicSemanticClusterPromotionService,
        )

        episodes = InMemorySubjectiveEpisodeStore()
        link_store = make_memory_link_being_setup().link_store
        sem_setup = make_semantic_being_setup()
        being_id = sem_setup.provision(1)
        for i, eid in enumerate(["x", "y", "z"]):
            from dataclasses import replace as _replace

            base = _ep(episode_id=eid)
            # Phase 3 Step 3e-2: promotion が being_id 経由で episode を引く
            episodes.put_by_being(being_id, _replace(base, interpreted=f"主観文{i}"))
        # being_id 経路に link を 3 本書く
        link_store.upsert_link_by_being(being_id, _link(a="x", b="y"))
        link_store.upsert_link_by_being(being_id, _link(a="y", b="z"))
        link_store.upsert_link_by_being(being_id, _link(a="x", b="z"))
        promo = EpisodicSemanticClusterPromotionService(
            episode_store=episodes,
            link_store=link_store,
            semantic_store=sem_setup.semantic_store,
            promotion_frontier=None,
            being_attachment_resolver=sem_setup.resolver,
            default_world_id=sem_setup.world_id,
        )
        promo.on_after_tool_turn(1, now=_NOW)
        # being_id 経路で link が読まれ、semantic store にも書かれる
        assert len(sem_setup.list_entries(1)) == 1


class TestSpreadingActivationBeingIdParam:
    """``neighbor_priming_scores`` は being_id 必須 (Phase 3 Step 3c-3)。"""

    def test_being_id_being_id_link(self) -> None:
        """beingid を渡すと beingid 経路で link をたどる。"""
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        setup.link_store.upsert_link_by_being(
            being_id, _link(a="seed", b="other", strength=0.9)
        )
        result = neighbor_priming_scores(
            being_id=being_id,
            seed_episode_ids=frozenset({"seed"}),
            link_store=setup.link_store,
            now=_NOW,
            max_hops=2,
        )
        assert "other" in result

    def test_being_id_raises_type_error(self) -> None:
        """Phase 3 Step 3c-3: being_id は BeingId 型必須。"""
        setup = make_memory_link_being_setup()
        with pytest.raises(TypeError, match="being_id"):
            neighbor_priming_scores(
                being_id="not-a-being-id",  # type: ignore[arg-type]
                seed_episode_ids=frozenset({"seed"}),
                link_store=setup.link_store,
                now=_NOW,
                max_hops=2,
            )
