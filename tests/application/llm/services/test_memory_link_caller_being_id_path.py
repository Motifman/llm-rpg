"""Phase 3 Step 3c-2: memory_link caller dual-path テスト。

Resolver+WorldId 注入 + Being provision 時に、5 caller のいずれもが
``*_by_being`` API 経由で動作することを確認する。memo 3a-2 / semantic 3b-2
と同じパターン。
"""

from __future__ import annotations

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

    def test_on_episode_committed_は_being_id_経路で_link_を作る(self) -> None:
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
        episodes.put(prev)
        episodes.put(newest)
        svc.on_episode_committed(newest, now=_NOW)
        # being_id 経路に書かれる
        assert len(setup.link_store.list_all_links_for_being(being_id)) == 1
        # legacy 経路は空
        assert setup.link_store.list_all_links_for_player(1) == []

    def test_resolver_未注入なら_legacy_経路で_link_を作る(self) -> None:
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        # Resolver 注入なし
        svc = EpisodicMemoryLinkApplicationService(episodes, setup.link_store)
        from datetime import timedelta as _td
        prev = _ep(episode_id="prev", occurred_at=_NOW - _td(minutes=5))
        newest = _ep(episode_id="newest", occurred_at=_NOW)
        episodes.put(prev)
        episodes.put(newest)
        svc.on_episode_committed(newest, now=_NOW)
        assert len(setup.link_store.list_all_links_for_player(1)) == 1


class TestEpisodicMemoryExploreToolExecutorDualPath:
    """``EpisodicMemoryExploreToolExecutor`` が being_id 経路で link を引く。"""

    def test_being_id_経由で_書いた_link_が_explore_で_見える(self) -> None:
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        episodes.put(_ep(episode_id="seed"))
        episodes.put(_ep(episode_id="other"))
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

    def test_being_id_注入時は_spreading_が_being_id_経路で_動く(self) -> None:
        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        seed_ep = _ep(episode_id="seed")
        far_ep = _ep(episode_id="far")
        episodes.put(seed_ep)
        episodes.put(far_ep)
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


class TestSpreadingActivationBeingIdParam:
    """``neighbor_priming_scores`` の being_id 引数が ``*_by_being`` 経路を駆動する。"""

    def test_being_id_を_渡すと_being_id_経路で_link_を_たどる(self) -> None:
        setup = make_memory_link_being_setup()
        being_id = setup.provision(1)
        setup.link_store.upsert_link_by_being(
            being_id, _link(a="seed", b="other", strength=0.9)
        )
        # legacy 側には何もない
        result = neighbor_priming_scores(
            player_id=1,
            seed_episode_ids=frozenset({"seed"}),
            link_store=setup.link_store,
            now=_NOW,
            max_hops=2,
            being_id=being_id,
        )
        assert "other" in result

    def test_being_id_なしなら_legacy_経路_を_たどる(self) -> None:
        setup = make_memory_link_being_setup()
        # legacy 側に書く
        setup.link_store.upsert_link(_link(a="seed", b="legacy_other"))
        result = neighbor_priming_scores(
            player_id=1,
            seed_episode_ids=frozenset({"seed"}),
            link_store=setup.link_store,
            now=_NOW,
            max_hops=2,
            being_id=None,
        )
        assert "legacy_other" in result
