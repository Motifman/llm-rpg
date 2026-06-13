"""エピソードリンクストア・サービス・受動想起をまとめて生成する。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    IEpisodicEpisodeStore,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    IMemoryLinkStore,
)
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import (
    ISemanticMemoryStore,
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

    episode_store: IEpisodicEpisodeStore
    link_store: IMemoryLinkStore
    link_service: EpisodicMemoryLinkApplicationService
    passive_recall: EpisodicPassiveRecallRetrievalService

    def memory_explore_executor(self) -> EpisodicMemoryExploreToolExecutor:
        return EpisodicMemoryExploreToolExecutor(
            episode_store=self.episode_store,
            link_store=self.link_store,
            link_service=self.link_service,
        )


def default_link_and_semantic_stores_for_episode_store(
    episode_store: IEpisodicEpisodeStore,
) -> tuple[IMemoryLinkStore, ISemanticMemoryStore]:
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
    episode_store: IEpisodicEpisodeStore,
    *,
    link_store: IMemoryLinkStore | None = None,
    promotion_frontier: EpisodicPromotionFrontier | None = None,
) -> EpisodicMemoryLinkBundle:
    ls = link_store if link_store is not None else InMemoryMemoryLinkStore()
    link_service = EpisodicMemoryLinkApplicationService(
        episode_store, ls, promotion_frontier=promotion_frontier
    )
    passive_recall = EpisodicPassiveRecallRetrievalService(
        episode_store,
        link_store=ls,
    )
    return EpisodicMemoryLinkBundle(
        episode_store=episode_store,
        link_store=ls,
        link_service=link_service,
        passive_recall=passive_recall,
    )
