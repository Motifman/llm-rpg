"""Phase 3 Step 3a-2: memo を読む側が being_id 経路で store を引くことのテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.being.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.services.in_memory_memo_store import (
    InMemoryMemoStore,
)
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    MemoCompletionHintService,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


@pytest.fixture
def repo() -> InMemoryBeingRepository:
    return InMemoryBeingRepository()


@pytest.fixture
def memo_store() -> InMemoryMemoStore:
    return InMemoryMemoStore()


@pytest.fixture
def world_id() -> WorldId:
    return WorldId(1)


@pytest.fixture
def resolver(repo: InMemoryBeingRepository) -> BeingAttachmentResolver:
    return BeingAttachmentResolver(repo)


@pytest.fixture
def provisioning(repo: InMemoryBeingRepository) -> BeingProvisioningService:
    return BeingProvisioningService(repo)


class TestMemoCompletionHintServiceNewPath:
    """MemoCompletionHintService: 呼び出し側 BeingId で being_id store から read。"""

    def test_detect_being_id_store_memo(
        self,
        memo_store: InMemoryMemoStore,
        provisioning: BeingProvisioningService,
    ) -> None:
        """being store に memo を入れて、呼び出し側 BeingId で hint が引ける。"""
        being_id = provisioning.ensure_attached(PlayerId(2))
        memo_store.add_by_being(being_id, "りんごを採集する")

        service = MemoCompletionHintService(
            memo_store,
            similarity_threshold=0.3,
        )
        hint = service.detect(
            being_id,
            action_summary="採集する",
            result_summary="りんごを 3 個入手しました",
        ).hint
        assert hint is not None
        assert hint.memo.content == "りんごを採集する"
