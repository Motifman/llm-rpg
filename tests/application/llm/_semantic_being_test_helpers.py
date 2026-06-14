"""semantic caller テスト用の Being provisioning ヘルパー (Phase 3 Step 3b-3)。

Step 3b-3 で semantic store の legacy player_id keyed API が撤去されたため、
テスト側で Being repository / Resolver / Provisioning を毎回組み立てる
boilerplate を共通化する。memo の ``_memo_being_test_helpers.py`` と同じ
パターン。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


DEFAULT_TEST_WORLD_ID = WorldId(1)


@dataclass
class SemanticBeingTestSetup:
    """semantic caller テストで利用する Being 一式。

    ``semantic_store`` を caller に渡しつつ、``resolver`` + ``world_id`` も注入
    すれば being_id 経路が走る。``provision(player_id)`` で attach 済の
    ``BeingId`` を取得でき、``populate(player_id, entry)`` で legacy 経路 in-place
    の置き換え (= ``store.add(entry)`` 等価) ができる。
    """

    semantic_store: InMemorySemanticMemoryStore
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

    def populate(self, player_id: int, entry: SemanticMemoryEntry) -> None:
        """being_id 経路経由で entry を追加する (テスト用)。

        Step 3b-3 以降、semantic store への書き込みは全て being_id keyed API
        経由。player_id を PlayerId に昇格して Being を解決し ``add_by_being``
        に委譲する。
        """
        being_id = self.being_id_for(player_id)
        self.semantic_store.add_by_being(being_id, entry)

    def register_signature(self, player_id: int, signature: str) -> bool:
        """being_id 経路で cluster signature を登録 (テスト用)。"""
        being_id = self.being_id_for(player_id)
        return self.semantic_store.register_cluster_signature_if_new_by_being(
            being_id, signature
        )

    def list_entries(self, player_id: int) -> list[SemanticMemoryEntry]:
        """being_id 経路で entry 一覧を取得 (テスト用)。"""
        being_id = self.being_id_for(player_id)
        return self.semantic_store.list_for_being(being_id)


def make_semantic_being_setup(
    *,
    world_id: WorldId | None = None,
    semantic_store: InMemorySemanticMemoryStore | None = None,
) -> SemanticBeingTestSetup:
    """semantic caller テスト用の最小セットアップを返す。

    ``semantic_store`` を渡せば外部 store を共有可能 (= 既存テストが既に
    store を持っている場合の差し込み用)。
    """
    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    provisioning = BeingProvisioningService(repo)
    return SemanticBeingTestSetup(
        semantic_store=semantic_store or InMemorySemanticMemoryStore(),
        being_repository=repo,
        resolver=resolver,
        provisioning=provisioning,
        world_id=world_id or DEFAULT_TEST_WORLD_ID,
        provisioned_being_ids={},
    )


__all__ = [
    "DEFAULT_TEST_WORLD_ID",
    "SemanticBeingTestSetup",
    "make_semantic_being_setup",
]
