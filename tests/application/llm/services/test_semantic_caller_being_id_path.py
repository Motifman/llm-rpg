"""Phase 3 Step 3b-3: semantic caller 3 file の being_id 経路テスト。

Step 3b-2 で導入した dual-path のうち legacy fallback を 3b-3 で撤去したため、
本テストでも legacy 経路に関する分岐検証は削除し、新 API のみが動く前提に
揃える。memo の Step 3a-3 後の状態と同じ。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
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
        player_id=player_id, being_id=BeingId(f"being_w1_p{player_id}"),
        text=text,
        evidence_episode_ids=("ep-1",),
        confidence=0.7,
        created_at=datetime.now(timezone.utc),
        importance_score=8,
        tags=tags,
    )

