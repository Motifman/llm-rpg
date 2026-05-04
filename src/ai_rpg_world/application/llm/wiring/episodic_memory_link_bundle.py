"""エピソードリンクストア・サービス・受動想起をまとめて生成する。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import (
    IEpisodicEpisodeStore,
)
from ai_rpg_world.application.llm.contracts.episodic_memory_link_store_port import (
    IMemoryLinkStore,
)
from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.executors.episodic_memory_explore_tool_executor import (
    EpisodicMemoryExploreToolExecutor,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
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


def build_episodic_memory_link_bundle(
    episode_store: IEpisodicEpisodeStore,
) -> EpisodicMemoryLinkBundle:
    link_store = InMemoryMemoryLinkStore()
    link_service = EpisodicMemoryLinkApplicationService(episode_store, link_store)
    passive_recall = EpisodicPassiveRecallRetrievalService(
        episode_store,
        link_store=link_store,
    )
    return EpisodicMemoryLinkBundle(
        episode_store=episode_store,
        link_store=link_store,
        link_service=link_service,
        passive_recall=passive_recall,
    )
