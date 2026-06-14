"""セマンティック昇格のフロンティア駆動（部分グラフ）と全域スキャンの一致・差分の検証。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import MemoryLink, MemoryLinkType
from ai_rpg_world.application.llm.services.episodic_promotion_frontier import EpisodicPromotionFrontier
from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
    EpisodicSemanticClusterPromotionService,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import InMemorySemanticMemoryStore
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from tests.application.llm._semantic_being_test_helpers import (
    make_semantic_being_setup,
)


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


def test_incremental_promotion_matches_full_scan_for_triangle() -> None:
    now = datetime.now(timezone.utc)

    def run(*, use_frontier: bool) -> list[str]:
        store = InMemorySubjectiveEpisodeStore()
        links = InMemoryMemoryLinkStore()
        # Phase 3 Step 3b-3 / 3c-2: semantic + link 共に being_id 経路必須。
        setup = make_semantic_being_setup()
        being_id = setup.provision(1)
        frontier = EpisodicPromotionFrontier() if use_frontier else None
        promo = EpisodicSemanticClusterPromotionService(
            episode_store=store,
            link_store=links,
            semantic_store=setup.semantic_store,
            promotion_frontier=frontier,
            expansion_hops=4,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        for i, eid in enumerate(["x", "y", "z"]):
            ep = _ep(episode_id=eid, player_id=1, recall_count=4, interpreted=f"t{i}")
            store.put(ep)
        links.upsert_link_by_being(being_id, _strong_link(1, "x", "y"))
        links.upsert_link_by_being(being_id, _strong_link(1, "y", "z"))
        links.upsert_link_by_being(being_id, _strong_link(1, "x", "z"))
        if frontier is not None:
            frontier.add(1, "x")
        promo.on_after_tool_turn(1, now=now)
        return [e.text for e in setup.list_entries(1)]

    full = run(use_frontier=False)
    incr = run(use_frontier=True)
    assert full == incr
    assert len(full) == 1


def test_incremental_zero_hops_misses_distant_cluster() -> None:
    now = datetime.now(timezone.utc)
    store = InMemorySubjectiveEpisodeStore()
    links = InMemoryMemoryLinkStore()
    setup = make_semantic_being_setup()
    being_id = setup.provision(1)
    frontier = EpisodicPromotionFrontier()
    frontier.add(1, "x")
    promo = EpisodicSemanticClusterPromotionService(
        episode_store=store,
        link_store=links,
        semantic_store=setup.semantic_store,
        promotion_frontier=frontier,
        expansion_hops=0,
        being_attachment_resolver=setup.resolver,
        default_world_id=setup.world_id,
    )
    for i, eid in enumerate(["x", "y", "z"]):
        ep = _ep(episode_id=eid, player_id=1, recall_count=4, interpreted=f"t{i}")
        store.put(ep)
    links.upsert_link_by_being(being_id, _strong_link(1, "x", "y"))
    links.upsert_link_by_being(being_id, _strong_link(1, "y", "z"))
    links.upsert_link_by_being(being_id, _strong_link(1, "x", "z"))
    promo.on_after_tool_turn(1, now=now)
    assert len(setup.list_entries(1)) == 0


def test_empty_frontier_falls_back_to_full_scan() -> None:
    """シードが無い場合は従来どおり全リンク走査する。"""
    now = datetime.now(timezone.utc)
    store = InMemorySubjectiveEpisodeStore()
    links = InMemoryMemoryLinkStore()
    setup = make_semantic_being_setup()
    being_id = setup.provision(1)
    frontier = EpisodicPromotionFrontier()
    promo = EpisodicSemanticClusterPromotionService(
        episode_store=store,
        link_store=links,
        semantic_store=setup.semantic_store,
        promotion_frontier=frontier,
        expansion_hops=4,
        being_attachment_resolver=setup.resolver,
        default_world_id=setup.world_id,
    )
    for i, eid in enumerate(["x", "y", "z"]):
        ep = _ep(episode_id=eid, player_id=1, recall_count=4, interpreted=f"t{i}")
        store.put(ep)
    links.upsert_link_by_being(being_id, _strong_link(1, "x", "y"))
    links.upsert_link_by_being(being_id, _strong_link(1, "y", "z"))
    links.upsert_link_by_being(being_id, _strong_link(1, "x", "z"))
    promo.on_after_tool_turn(1, now=now)
    assert len(setup.list_entries(1)) == 1

