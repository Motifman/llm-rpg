"""クラスタ昇格の FAMILIARITY evidence 転用モード (U3b) の検証。

``belief_evidence_buffer_store`` 注入時のみ挙動が変わる。未注入 (flag OFF
相当) では既存の store 直書き + recall_count>=3 ゲートを完全に維持する
(= 並存期間の後方互換)。
"""

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
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
    EpisodicSemanticClusterPromotionService,
    MIN_RECALL_COUNT,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
)
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
        action=EpisodeAction(tool_name="world_explore"),
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


def _strong_link(player_id: int, a: str, b: str, *, strength: float = 0.9) -> MemoryLink:
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


def _build_triangle_cluster(
    *,
    recall_count: int,
    belief_evidence_buffer_store=None,
) -> tuple[EpisodicSemanticClusterPromotionService, object, int]:
    store = InMemorySubjectiveEpisodeStore()
    links = InMemoryMemoryLinkStore()
    setup = make_semantic_being_setup()
    being_id = setup.provision(1)
    promo = EpisodicSemanticClusterPromotionService(
        episode_store=store,
        link_store=links,
        semantic_store=setup.semantic_store,
        being_attachment_resolver=setup.resolver,
        default_world_id=setup.world_id,
        belief_evidence_buffer_store=belief_evidence_buffer_store,
    )
    for i, eid in enumerate(["x", "y", "z"]):
        ep = _ep(episode_id=eid, player_id=1, recall_count=recall_count, interpreted=f"t{i}")
        store.put_by_being(being_id, ep)
    links.upsert_link_by_being(being_id, _strong_link(1, "x", "y"))
    links.upsert_link_by_being(being_id, _strong_link(1, "y", "z"))
    links.upsert_link_by_being(being_id, _strong_link(1, "x", "z"))
    return promo, setup, being_id


class TestFamiliarityModeDisabled:
    """belief_evidence_buffer_store 未注入 (flag OFF 相当) では現行挙動が完全に不変。"""

    def test_writes_directly_to_semantic_store_when_gate_satisfied(self) -> None:
        """recall_count>=3 を満たすクラスタは、従来どおり semantic store に直書きされる。"""
        promo, setup, being_id = _build_triangle_cluster(recall_count=MIN_RECALL_COUNT)

        promo.on_after_tool_turn(1)

        assert len(setup.list_entries(1)) == 1

    def test_gate_blocks_promotion_when_recall_count_insufficient(self) -> None:
        """recall_count がゲート未満なら、直書きモードでは昇格されない。"""
        promo, setup, being_id = _build_triangle_cluster(recall_count=MIN_RECALL_COUNT - 1)

        promo.on_after_tool_turn(1)

        assert setup.list_entries(1) == []


class TestFamiliarityModeEnabled:
    """belief_evidence_buffer_store 注入時は FAMILIARITY evidence を emit し、
    store 直書き・recall_count ゲートの両方をやめる。"""

    def test_emits_familiarity_evidence_instead_of_writing_semantic_store(self) -> None:
        """クラスタ検出時、semantic store には何も書かれず、evidence buffer に
        FAMILIARITY evidence が 1 件積まれる。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        promo, setup, being_id = _build_triangle_cluster(
            recall_count=MIN_RECALL_COUNT,
            belief_evidence_buffer_store=buffer_store,
        )

        promo.on_after_tool_turn(1)

        assert setup.list_entries(1) == []
        evidences = buffer_store.list_all_by_being(being_id)
        assert len(evidences) == 1
        assert evidences[0].source_kind == BeliefEvidenceSourceKind.FAMILIARITY
        assert set(evidences[0].episode_ids) == {"x", "y", "z"}

    def test_recall_count_gate_is_disabled(self) -> None:
        """FAMILIARITY モードでは recall_count がゲート未満のクラスタも
        evidence 化される (学習のゲートではなく想起の spreading に純化)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        promo, setup, being_id = _build_triangle_cluster(
            recall_count=0,
            belief_evidence_buffer_store=buffer_store,
        )

        promo.on_after_tool_turn(1)

        assert len(buffer_store.list_all_by_being(being_id)) == 1

    def test_same_cluster_signature_is_not_emitted_twice(self) -> None:
        """同一クラスタは cluster_signature 登録で重複 emit を防ぐ (直書きモードと同じ規約)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        promo, setup, being_id = _build_triangle_cluster(
            recall_count=MIN_RECALL_COUNT,
            belief_evidence_buffer_store=buffer_store,
        )

        promo.on_after_tool_turn(1)
        promo.on_after_tool_turn(1)

        assert len(buffer_store.list_all_by_being(being_id)) == 1
