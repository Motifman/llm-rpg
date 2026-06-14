"""エピソードリンクストア・共想起・セマンティック昇格のユニット検証。"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import MemoryLink, MemoryLinkType
from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallCandidate,
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
    EpisodicSemanticClusterPromotionService,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from tests.application.llm._memory_link_being_test_helpers import (
    make_memory_link_being_setup,
)
from uuid import uuid4


def _ep(
    *,
    episode_id: str,
    player_id: int,
    recall_count: int = 0,
    interpreted: str | None = "解釈",
) -> SubjectiveEpisode:
    cue = EpisodicCue(axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=datetime.now(timezone.utc),
        game_time_label="12:00",
        source=EpisodeSource(event_ids=("e1",)),
        location=EpisodeLocation(spot_id=1),
        action=EpisodeAction(tool_name="world_no_op"),
        who=("self",),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=interpreted,
        cues=(cue,),
        recall_text="r",
        recall_count=recall_count,
        last_recalled_at=None,
    )


def test_temporal_link_created_between_recent_pair() -> None:
    """Phase 3 Step 3c-3: link 書き込みは being_id keyed only。Resolver 注入必須。"""
    store = InMemorySubjectiveEpisodeStore()
    setup = make_memory_link_being_setup()
    being_id = setup.provision(7)
    svc = EpisodicMemoryLinkApplicationService(
        store,
        setup.link_store,
        being_attachment_resolver=setup.resolver,
        default_world_id=setup.world_id,
    )
    first = _ep(episode_id="e1", player_id=7)
    second = _ep(episode_id="e2", player_id=7)
    # Phase 3 Step 3e-2: link service が being_id 経由で list_recent
    store.put_by_being(being_id, first)
    store.put_by_being(being_id, second)
    svc.on_episode_committed(second)
    assert store.list_recent_by_being(being_id, 2)[0].episode_id == "e2"
    assert (
        setup.link_store.get_link_by_being(
            being_id, "e1", "e2", MemoryLinkType.TEMPORAL
        )
        is not None
    )


def test_passive_recall_triggers_co_recall_links() -> None:
    store = InMemorySubjectiveEpisodeStore()
    setup = make_memory_link_being_setup()
    being_id = setup.provision(1)
    link_svc = EpisodicMemoryLinkApplicationService(
        store,
        setup.link_store,
        being_attachment_resolver=setup.resolver,
        default_world_id=setup.world_id,
    )
    pr = EpisodicPassiveRecallRetrievalService(
        store,
        link_store=setup.link_store,
        being_attachment_resolver=setup.resolver,
        default_world_id=setup.world_id,
    )
    e1 = _ep(episode_id="a", player_id=1)
    e2 = _ep(episode_id="b", player_id=1)
    store.put_by_being(being_id, e1)
    store.put_by_being(being_id, e2)
    cue = EpisodicCue(axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
    res = pr.retrieve(
        player_id=1,
        situation_cues=(cue,),
        limit_per_axis=5,
        max_candidates=5,
    )
    link_svc.on_passive_recall_candidates(1, res.candidates)
    assert (
        setup.link_store.get_link_by_being(
            being_id, "a", "b", MemoryLinkType.CO_RECALL
        )
        is not None
    )


def _strong_link(
    player_id: int,
    a: str,
    b: str,
    *,
    strength: float = 0.9,
) -> MemoryLink:
    now = datetime.now(timezone.utc)
    na, nb = (a, b) if a < b else (b, a)
    return MemoryLink(
        link_id=f"memlink-{uuid4().hex}",
        player_id=player_id,
        episode_id_a=na,
        episode_id_b=nb,
        link_type=MemoryLinkType.CO_RECALL,
        strength=strength,
        co_activation_count=1,
        created_at=now,
        last_activated_at=now,
        decay_rate=0.001,
    )


def test_semantic_cluster_promotion_writes_store() -> None:
    from tests.application.llm._semantic_being_test_helpers import (
        make_semantic_being_setup,
    )

    store = InMemorySubjectiveEpisodeStore()
    links = InMemoryMemoryLinkStore()
    # Phase 3 Step 3b-3: semantic は being_id 経路必須。
    # Phase 3 Step 3c-2: cluster promotion が Resolver 注入時に link store も
    # `*_by_being` で読みにいくため、links 側も同じ being_id で書く必要がある。
    setup = make_semantic_being_setup()
    being_id = setup.provision(1)
    promo = EpisodicSemanticClusterPromotionService(
        episode_store=store,
        link_store=links,
        semantic_store=setup.semantic_store,
        being_attachment_resolver=setup.resolver,
        default_world_id=setup.world_id,
    )
    for i, eid in enumerate(["x", "y", "z"]):
        ep = _ep(episode_id=eid, player_id=1, recall_count=4, interpreted=f"t{i}")
        store.put_by_being(being_id, ep)
    now = datetime.now(timezone.utc)
    links.upsert_link_by_being(being_id, _strong_link(1, "x", "y"))
    links.upsert_link_by_being(being_id, _strong_link(1, "y", "z"))
    links.upsert_link_by_being(being_id, _strong_link(1, "x", "z"))
    promo.on_after_tool_turn(1, now=now)
    assert len(setup.list_entries(1)) == 1


def test_link_store_lists_all_for_being() -> None:
    setup = make_memory_link_being_setup()
    being_id = setup.provision(3)
    setup.link_store.upsert_link_by_being(being_id, _strong_link(3, "a", "b"))
    assert len(setup.link_store.list_all_links_for_being(being_id)) == 1


def test_memory_link_store_supports_co_recall_candidates_tuple() -> None:
    store = InMemorySubjectiveEpisodeStore()
    setup = make_memory_link_being_setup()
    being_id = setup.provision(2)
    link_svc = EpisodicMemoryLinkApplicationService(
        store,
        setup.link_store,
        being_attachment_resolver=setup.resolver,
        default_world_id=setup.world_id,
    )
    e1 = _ep(episode_id="p", player_id=2)
    e2 = _ep(episode_id="q", player_id=2)
    store.put_by_being(being_id, e1)
    store.put_by_being(being_id, e2)
    cands = (
        EpisodicPassiveRecallCandidate(episode=e1, source_axes=("temporal",)),
        EpisodicPassiveRecallCandidate(episode=e2, source_axes=("temporal",)),
    )
    link_svc.on_passive_recall_candidates(2, cands)
    assert (
        setup.link_store.get_link_by_being(
            being_id, "p", "q", MemoryLinkType.CO_RECALL
        )
        is not None
    )
