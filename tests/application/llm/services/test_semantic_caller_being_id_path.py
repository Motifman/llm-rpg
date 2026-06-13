"""Phase 3 Step 3b-2: semantic caller 3 file の dual-path 新 API 経路テスト。

Resolver + WorldId を注入したときに ``*_by_being`` API 経路が走ることを確認する。
memo の Step 3a-2 と同じパターン。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
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
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
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

    def test_retrieve_は_being_id_store_の_entry_を見る(
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
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        result = service.retrieve(
            player_id=2,
            situation_cues=(
                EpisodicCue(
                    axis="object", value="apple", source=EpisodicCueSource.TOOL
                ),
            ),
            top_k=5,
        )
        assert len(result) == 1
        assert result[0].entry.text == "りんご"

    def test_未_provision_なら_legacy_経路に_fallback(
        self,
        store: InMemorySemanticMemoryStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
    ) -> None:
        """Resolver 注入 + Being 未 provision なら legacy 経路で動く。"""
        store.add(_make_entry(text="legacy 側"))
        service = SemanticPassiveRecallService(
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        result = service.retrieve(
            player_id=2,
            situation_cues=(),
            top_k=5,
        )
        # legacy store にあるので fallback で取れる
        assert len(result) == 1


class TestSemanticMemorySearchToolExecutorNewPath:
    """SemanticMemorySearchToolExecutor: Resolver 注入時の検索経路。"""

    def test_search_は_being_id_store_の_entry_を検索する(
        self,
        store: InMemorySemanticMemoryStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
        provisioning: BeingProvisioningService,
    ) -> None:
        """being store に登録した entry が memory_search_semantic で見つかる。"""
        being_id = provisioning.ensure_attached(PlayerId(2))
        store.add_by_being(
            being_id, _make_entry(text="りんご園で 3 個入手", tags=("apple",))
        )

        executor = SemanticMemorySearchToolExecutor(
            semantic_store=store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        handlers = executor.get_handlers()
        result = handlers[TOOL_NAME_MEMORY_SEARCH_SEMANTIC](
            2, {"query": "りんご", "top_k": 5}
        )
        assert result.success is True
        payload = json.loads(result.message)
        assert len(payload["matched_entries"]) == 1
        assert "りんご" in payload["matched_entries"][0]["summary"]


class TestEpisodicSemanticClusterPromotionServiceNewPath:
    """EpisodicSemanticClusterPromotionService の dual-path 内部ヘルパー検証。

    full promotion フローは複雑な事前条件 (= 強リンク・3 件以上 episode 等) を
    要するため、本テストでは ``_register_signature`` / ``_add_entry`` の単体
    挙動だけ確認する。

    TODO (Phase 3 Step 3b-3): legacy 撤去で dual-path helper を消すとき、本テスト
    も併せて整理する。``on_after_tool_turn`` 経由の integration test を 1 件
    追加する案もあり (= リファクタリング耐性 ↑)。private API 直呼びはステップ
    完了時に再評価する。
    """

    def test_register_signature_は_being_id_store_に書く(
        self,
        store: InMemorySemanticMemoryStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
        provisioning: BeingProvisioningService,
    ) -> None:
        """provision 済 Being があれば being_id 経路で signature 登録される。"""
        provisioning.ensure_attached(PlayerId(2))

        from unittest.mock import MagicMock

        service = EpisodicSemanticClusterPromotionService(
            episode_store=MagicMock(),
            link_store=MagicMock(),
            semantic_store=store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        # 初回 True、2 回目 False
        assert service._register_signature(2, "sig-1") is True
        assert service._register_signature(2, "sig-1") is False
        # being store に登録されたことを確認 (= legacy 側は登録されていない)
        assert (
            store.register_cluster_signature_if_new(2, "sig-1") is True
        )  # legacy 側は未登録なので初回扱い

    def test_add_entry_は_being_id_store_に書く(
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
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        entry = _make_entry()
        service._add_entry(2, entry)
        # being store に入る
        assert len(store.list_for_being(being_id)) == 1
        # legacy 側は空
        assert store.list_for_player(2) == []
