"""reinterpretation caller テスト用の Being provisioning ヘルパー
(Phase 3 Step 3d-2)。

memo / semantic / memory_link と同型。Resolver+WorldId 注入 +
provision 済 Being を 1 セットで用意する。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
    InMemoryEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


DEFAULT_TEST_WORLD_ID = WorldId(1)


@dataclass
class ReinterpretationBeingTestSetup:
    """reinterpretation caller テスト用の Being 一式 + 2 store。"""

    recall_buffer: InMemoryEpisodicRecallBufferStore
    journal: InMemoryEpisodicReinterpretationJournalStore
    being_repository: InMemoryBeingRepository
    resolver: BeingAttachmentResolver
    provisioning: BeingProvisioningService
    world_id: WorldId
    provisioned_being_ids: dict[PlayerId, BeingId]

    def provision(self, player_id: int) -> BeingId:
        pid = PlayerId(player_id)
        being_id = self.provisioning.ensure_attached(pid)
        self.provisioned_being_ids[pid] = being_id
        return being_id


def make_reinterpretation_being_setup(
    *,
    world_id: WorldId | None = None,
) -> ReinterpretationBeingTestSetup:
    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    provisioning = BeingProvisioningService(repo)
    return ReinterpretationBeingTestSetup(
        recall_buffer=InMemoryEpisodicRecallBufferStore(),
        journal=InMemoryEpisodicReinterpretationJournalStore(),
        being_repository=repo,
        resolver=resolver,
        provisioning=provisioning,
        world_id=world_id or DEFAULT_TEST_WORLD_ID,
        provisioned_being_ids={},
    )


__all__ = [
    "DEFAULT_TEST_WORLD_ID",
    "ReinterpretationBeingTestSetup",
    "make_reinterpretation_being_setup",
]
