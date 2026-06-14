"""エピソードリンクストア・サービス・受動想起をまとめて生成する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ai_rpg_world.domain.being.service.being_attachment_resolver import (
        BeingAttachmentResolver,
    )
    from ai_rpg_world.domain.world.value_object.world_id import WorldId

from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    MemoryLinkRepository,
)
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import (
    SemanticMemoryRepository,
)
from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.episodic_promotion_frontier import (
    EpisodicPromotionFrontier,
)
from ai_rpg_world.application.llm.services.executors.episodic_memory_explore_tool_executor import (
    EpisodicMemoryExploreToolExecutor,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)


@dataclass(frozen=True)
class EpisodicMemoryLinkBundle:
    """共有リンクストア・リンクサービス・拡散活性化付き受動想起。"""

    episode_store: EpisodicEpisodeRepository
    link_store: MemoryLinkRepository
    link_service: EpisodicMemoryLinkApplicationService
    passive_recall: EpisodicPassiveRecallRetrievalService
    # Phase 3 Step 3c-2: memory_explore_executor() で being_id 経路を有効化する
    # ために、bundle 構築時点で Resolver+WorldId を握っておく。未注入なら
    # legacy 経路で動く。
    being_attachment_resolver: Optional["BeingAttachmentResolver"] = None
    default_world_id: Optional["WorldId"] = None

    def memory_explore_executor(self) -> EpisodicMemoryExploreToolExecutor:
        return EpisodicMemoryExploreToolExecutor(
            episode_store=self.episode_store,
            link_store=self.link_store,
            link_service=self.link_service,
            being_attachment_resolver=self.being_attachment_resolver,
            default_world_id=self.default_world_id,
        )


def default_link_and_semantic_stores_for_episode_store(
    episode_store: EpisodicEpisodeRepository,
) -> tuple[MemoryLinkRepository, SemanticMemoryRepository]:
    """
    エピソードストアが SqliteSubjectiveEpisodeStore のとき、同一 DB 接続に
    MemoryLink / セマンティック表を同居させる。それ以外はインメモリ。
    """
    from ai_rpg_world.infrastructure.repository.sqlite_subjective_episode_store import (
        SqliteSubjectiveEpisodeStore,
    )
    from ai_rpg_world.infrastructure.repository.sqlite_memory_link_store import (
        SqliteMemoryLinkStore,
    )
    from ai_rpg_world.infrastructure.repository.sqlite_semantic_memory_store import (
        SqliteSemanticMemoryStore,
    )

    if isinstance(episode_store, SqliteSubjectiveEpisodeStore):
        conn = episode_store.connection
        return SqliteMemoryLinkStore(conn), SqliteSemanticMemoryStore(conn)
    return InMemoryMemoryLinkStore(), InMemorySemanticMemoryStore()


def build_episodic_memory_link_bundle(
    episode_store: EpisodicEpisodeRepository,
    *,
    link_store: MemoryLinkRepository | None = None,
    promotion_frontier: EpisodicPromotionFrontier | None = None,
    being_attachment_resolver: Optional["BeingAttachmentResolver"] = None,
    default_world_id: Optional["WorldId"] = None,
) -> EpisodicMemoryLinkBundle:
    """Phase 3 Step 3c-2: Resolver+WorldId を受け取り、link_service /
    passive_recall / memory_explore_executor に伝播する。未注入なら legacy
    player_id 経路で動く (= 既存テスト互換)。
    """
    ls = link_store if link_store is not None else InMemoryMemoryLinkStore()
    link_service = EpisodicMemoryLinkApplicationService(
        episode_store,
        ls,
        promotion_frontier=promotion_frontier,
        being_attachment_resolver=being_attachment_resolver,
        default_world_id=default_world_id,
    )
    passive_recall = EpisodicPassiveRecallRetrievalService(
        episode_store,
        link_store=ls,
        being_attachment_resolver=being_attachment_resolver,
        default_world_id=default_world_id,
    )
    return EpisodicMemoryLinkBundle(
        episode_store=episode_store,
        link_store=ls,
        link_service=link_service,
        passive_recall=passive_recall,
        being_attachment_resolver=being_attachment_resolver,
        default_world_id=default_world_id,
    )
