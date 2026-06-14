"""memory_link caller テスト用の Being provisioning ヘルパー (Phase 3 Step 3c-2)。

Step 3c-2 で memory_link caller (`EpisodicMemoryLinkApplicationService` /
`EpisodicSemanticClusterPromotionService` / `EpisodicPassiveRecallRetrievalService`
/ `EpisodicMemoryExploreToolExecutor`) が dual-path 化したため、テストで
Resolver を注入したときに同じ Being で link 書き込みを行うヘルパーを
共通化する。memo / semantic と同じパターン。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
)
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import MemoryLink
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


DEFAULT_TEST_WORLD_ID = WorldId(1)


@dataclass
class MemoryLinkBeingTestSetup:
    """memory_link caller テスト用の Being 一式。"""

    link_store: InMemoryMemoryLinkStore
    being_repository: InMemoryBeingRepository
    resolver: BeingAttachmentResolver
    provisioning: BeingProvisioningService
    world_id: WorldId
    provisioned_being_ids: dict[PlayerId, BeingId]

    def provision(self, player_id: int) -> BeingId:
        """指定 PlayerId に Being を attach し BeingId を返す (idempotent)。"""
        pid = PlayerId(player_id)
        being_id = self.provisioning.ensure_attached(pid)
        self.provisioned_being_ids[pid] = being_id
        return being_id

    def being_id_for(self, player_id: int) -> BeingId:
        pid = PlayerId(player_id)
        if pid not in self.provisioned_being_ids:
            return self.provision(player_id)
        return self.provisioned_being_ids[pid]

    def upsert_link(self, player_id: int, link: MemoryLink) -> None:
        """being_id 経路経由で link を upsert (テスト用)。"""
        being_id = self.being_id_for(player_id)
        self.link_store.upsert_link_by_being(being_id, link)


def make_memory_link_being_setup(
    *,
    world_id: WorldId | None = None,
    link_store: InMemoryMemoryLinkStore | None = None,
) -> MemoryLinkBeingTestSetup:
    """memory_link caller テスト用の最小セットアップ。"""
    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    provisioning = BeingProvisioningService(repo)
    return MemoryLinkBeingTestSetup(
        link_store=link_store or InMemoryMemoryLinkStore(),
        being_repository=repo,
        resolver=resolver,
        provisioning=provisioning,
        world_id=world_id or DEFAULT_TEST_WORLD_ID,
        provisioned_being_ids={},
    )


__all__ = [
    "DEFAULT_TEST_WORLD_ID",
    "MemoryLinkBeingTestSetup",
    "make_memory_link_being_setup",
]
