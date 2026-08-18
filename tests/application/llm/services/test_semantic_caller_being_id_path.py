"""Phase 3 Step 3b-3: semantic caller 3 file の being_id 経路テスト。

Step 3b-2 で導入した dual-path のうち legacy fallback を 3b-3 で撤去したため、
本テストでも legacy 経路に関する分岐検証は削除し、新 API のみが動く前提に
揃える。memo の Step 3a-3 後の状態と同じ。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
    EpisodicSemanticClusterPromotionService,
)
from ai_rpg_world.application.llm.services.executors.semantic_memory_search_tool_executor import (
    SemanticMemorySearchToolExecutor,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
    SemanticPassiveRecallService,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_SEARCH_SEMANTIC,
)
from ai_rpg_world.application.being.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


@pytest.fixture
def store() -> InMemorySemanticMemoryStore:
    return InMemorySemanticMemoryStore()


@pytest.fixture
def world_id() -> WorldId:
    return WorldId(1)


@pytest.fixture
def being_repo() -> InMemoryBeingRepository:
    return InMemoryBeingRepository()


@pytest.fixture
def resolver(being_repo: InMemoryBeingRepository) -> BeingAttachmentResolver:
    return BeingAttachmentResolver(being_repo)


@pytest.fixture
def provisioning(being_repo: InMemoryBeingRepository) -> BeingProvisioningService:
    return BeingProvisioningService(being_repo)


def _make_entry(
    entry_id: str = "e1",
    player_id: int = 2,
    text: str = "りんご園で収穫した",
    tags: tuple[str, ...] = ("apple", "harvest"),
) -> SemanticMemoryEntry:
    return SemanticMemoryEntry(
        entry_id=entry_id,
        player_id=player_id,
        text=text,
        evidence_episode_ids=("ep-1",),
        confidence=0.7,
        created_at=datetime.now(timezone.utc),
        importance_score=8,
        tags=tags,
    )


class TestSemanticPassiveRecallServiceNewPath:
    """SemanticPassiveRecallService: Resolver 注入時に being_id store から読む。"""

    def test_retrieve_being_id_store_entry(
        self,
        store: InMemorySemanticMemoryStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
        provisioning: BeingProvisioningService,
    ) -> None:
        """being store に entry を入れて、Resolver 経由で retrieve できる。"""
        being_id = provisioning.ensure_attached(PlayerId(2))
        store.add_by_being(being_id, _make_entry(text="りんご"))

        service = SemanticPassiveRecallService(
            store,
        )
        result = service.retrieve(
            being_id=being_id,
            situation_cues=(
                EpisodicCue(
                    axis="object", value="apple", source=EpisodicCueSource.TOOL
                ),
            ),
            top_k=5,
        )
        assert len(result) == 1
        assert result[0].entry.text == "りんご"

    def test_provision_empty_store_returns_empty(
        self,
        store: InMemorySemanticMemoryStore,
        provisioning: BeingProvisioningService,
    ) -> None:
        """being store が空なら retrieve も空 list。"""
        being_id = provisioning.ensure_attached(PlayerId(2))
        service = SemanticPassiveRecallService(store)
        result = service.retrieve(
            being_id=being_id,
            situation_cues=(),
            top_k=5,
        )
        assert result == []

    def test_unprovisioned_being_store_empty(
        self,
        store: InMemorySemanticMemoryStore,
    ) -> None:
        """store に entry が無ければ空 list。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        service = SemanticPassiveRecallService(store)
        result = service.retrieve(
            being_id=BeingId("being_w1_p2"),
            situation_cues=(),
            top_k=5,
        )
        assert result == []


class TestSemanticMemorySearchToolExecutorNewPath:
    """SemanticMemorySearchToolExecutor: ActingBeing 経路の検索。"""

    def test_search_being_id_store_entry(
        self,
        store: InMemorySemanticMemoryStore,
        provisioning: BeingProvisioningService,
    ) -> None:
        """being store に登録した entry が memory_search_semantic で見つかる。"""
        being_id = provisioning.ensure_attached(PlayerId(2))
        store.add_by_being(
            being_id, _make_entry(text="りんご園で 3 個入手", tags=("apple",))
        )

        executor = SemanticMemorySearchToolExecutor(semantic_store=store)
        handlers = executor.get_handlers()
        acting = ActingBeing(player_id=PlayerId(2), being_id=being_id)
        result = handlers[TOOL_NAME_MEMORY_SEARCH_SEMANTIC](
            acting, {"query": "りんご", "top_k": 5}
        )
        assert result.success is True
        payload = json.loads(result.message)
        assert len(payload["matched_entries"]) == 1
        assert "りんご" in payload["matched_entries"][0]["summary"]

    def test_semantic_executor_has_no_being_attachment_resolver(
        self,
        store: InMemorySemanticMemoryStore,
    ) -> None:
        """SemanticMemorySearchToolExecutor は BeingAttachmentResolver を持たない。"""
        executor = SemanticMemorySearchToolExecutor(semantic_store=store)
        assert not hasattr(executor, "being_attachment_resolver")


class TestEpisodicSemanticClusterPromotionServiceNewPath:
    """EpisodicSemanticClusterPromotionService の being_id 経路内部ヘルパー検証。

    full promotion フローは複雑な事前条件 (= 強リンク・3 件以上 episode 等) を
    要するため、本テストでは ``_register_signature`` / ``_add_entry`` の単体
    挙動だけ確認する。``on_after_tool_turn`` 経由の integration カバレッジは
    ``test_episodic_memory_link_and_promotion`` / ``test_episodic_semantic_promotion_*``
    で別途取れている。
    """

    def test_register_signature_being_id_store(
        self,
        store: InMemorySemanticMemoryStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
        provisioning: BeingProvisioningService,
    ) -> None:
        """provision 済 Being があれば being_id 経路で signature 登録される。"""
        being_id = provisioning.ensure_attached(PlayerId(2))

        from unittest.mock import MagicMock

        service = EpisodicSemanticClusterPromotionService(
            episode_store=MagicMock(),
            link_store=MagicMock(),
            semantic_store=store,
        )
        # 初回 True、2 回目 False
        assert service._register_signature(being_id, "sig-1") is True
        assert service._register_signature(being_id, "sig-1") is False
        # 直接 being_id 経由で再登録試行 → False (= being store に入っている証拠)
        assert (
            store.register_cluster_signature_if_new_by_being(being_id, "sig-1")
            is False
        )

    def test_add_entry_being_id_store(
        self,
        store: InMemorySemanticMemoryStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
        provisioning: BeingProvisioningService,
    ) -> None:
        """provision 済 Being があれば being_id 経路で entry 追加される。"""
        being_id = provisioning.ensure_attached(PlayerId(2))

        from unittest.mock import MagicMock

        service = EpisodicSemanticClusterPromotionService(
            episode_store=MagicMock(),
            link_store=MagicMock(),
            semantic_store=store,
        )
        entry = _make_entry()
        service._add_entry(being_id, entry)
        assert len(store.list_for_being(being_id)) == 1

    def test_being_id_direct_helpers(
        self,
        store: InMemorySemanticMemoryStore,
        being_repo: InMemoryBeingRepository,
    ) -> None:
        """内部 helper は being_id を直接受け取り、store に書き込む。"""
        from unittest.mock import MagicMock

        provisioning = BeingProvisioningService(being_repo)
        being_id = provisioning.ensure_attached(PlayerId(99))

        service = EpisodicSemanticClusterPromotionService(
            episode_store=MagicMock(),
            link_store=MagicMock(),
            semantic_store=store,
        )
        assert service._register_signature(being_id, "sig-x") is True
        service._add_entry(being_id, _make_entry(player_id=99))
        assert len(store.list_for_being(being_id)) == 1
        assert (
            store.register_cluster_signature_if_new_by_being(being_id, "sig-x")
            is False
        )
