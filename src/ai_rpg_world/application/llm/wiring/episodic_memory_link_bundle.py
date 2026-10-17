"""エピソードリンクストア・サービス・受動想起をまとめて生成する。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    MemoryLinkRepository,
)


@dataclass(frozen=True)
class EpisodicMemoryLinkBundle:
    """共有リンクストア・リンクサービス・拡散活性化付き受動想起。

    本 bundle は ``build_episodic_memory_link_bundle`` factory 経由でのみ
    生成される想定なので、引数バリデーションはせず factory 側に委ねる
    (= 他 caller の dataclass が ``__post_init__`` で型ガードしているのと
    方針が異なる。wiring 層 dataclass は構築規律を factory に集約する)。
    """

    episode_store: EpisodicEpisodeRepository
    link_store: MemoryLinkRepository
    link_service: EpisodicMemoryLinkApplicationService
    passive_recall: EpisodicPassiveRecallRetrievalService

def default_link_store_for_episode_store(
    episode_store: EpisodicEpisodeRepository,
) -> MemoryLinkRepository:
    """
    エピソードストアが SqliteSubjectiveEpisodeStore のとき、同一 DB 接続に
    MemoryLink 表を同居させる。それ以外はインメモリ。
    """
    from ai_rpg_world.infrastructure.repository.sqlite_memory_link_store import (
        SqliteMemoryLinkStore,
    )
    from ai_rpg_world.infrastructure.repository.sqlite_subjective_episode_store import (
        SqliteSubjectiveEpisodeStore,
    )

    if isinstance(episode_store, SqliteSubjectiveEpisodeStore):
        conn = episode_store.connection
        return SqliteMemoryLinkStore(conn)
    return InMemoryMemoryLinkStore()


def build_episodic_memory_link_bundle(
    episode_store: EpisodicEpisodeRepository,
    *,
    link_store: MemoryLinkRepository | None = None,
) -> EpisodicMemoryLinkBundle:
    """link_service / passive_recall を組み立てる。"""
    ls = link_store if link_store is not None else InMemoryMemoryLinkStore()
    link_service = EpisodicMemoryLinkApplicationService(episode_store, ls)
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
