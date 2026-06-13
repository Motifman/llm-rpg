"""memo caller テスト用の Being provisioning ヘルパー (Phase 3 Step 3a-3)。

Step 3a-3 で memo caller が Resolver+WorldId を required にしたため、テスト側で
Being repository / Resolver / Provisioning を毎回組み立てる boilerplate を
共通化する。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.services.in_memory_memo_store import (
    InMemoryMemoStore,
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
class MemoBeingTestSetup:
    """memo caller テストで利用する Being 一式。

    memo_store + Resolver + WorldId を caller に渡せば being_id 経路が走る。
    provisioned_being_ids には ``provision(player_id)`` で attach 済の BeingId
    が記録される (= 任意で memo_store.add_by_being() に直接使える)。
    """

    memo_store: InMemoryMemoStore
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
        """既に provision 済の BeingId を返す (= 未 provision なら ensure_attached)。"""
        pid = PlayerId(player_id)
        if pid not in self.provisioned_being_ids:
            return self.provision(player_id)
        return self.provisioned_being_ids[pid]


def make_memo_being_setup(
    *,
    world_id: WorldId | None = None,
    memo_store: InMemoryMemoStore | None = None,
) -> MemoBeingTestSetup:
    """memo caller テスト用の最小セットアップを返す。

    ``memo_store`` を渡せば外部 store を共有可能 (= 既存テストが既に store を
    持っている場合の差し込み用)。
    """
    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    provisioning = BeingProvisioningService(repo)
    return MemoBeingTestSetup(
        memo_store=memo_store or InMemoryMemoStore(),
        being_repository=repo,
        resolver=resolver,
        provisioning=provisioning,
        world_id=world_id or DEFAULT_TEST_WORLD_ID,
        provisioned_being_ids={},
    )


__all__ = [
    "DEFAULT_TEST_WORLD_ID",
    "MemoBeingTestSetup",
    "make_memo_being_setup",
]
