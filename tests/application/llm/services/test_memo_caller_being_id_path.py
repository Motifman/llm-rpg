"""Phase 3 Step 3a-2: memo caller 3 file の dual-path 新 API 経路テスト。

Resolver + WorldId を注入したときに ``*_by_being`` API 経路が走ることを確認する。
既存テストは未注入 (= legacy player_id API) を網羅しているので、本テストは
新経路のみに集中する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.services.executors.memo_executor import (
    MemoToolExecutor,
)
from ai_rpg_world.application.llm.services.in_memory_memo_store import (
    InMemoryMemoStore,
)
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    MemoCompletionHintService,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
    TOOL_NAME_MEMO_LIST,
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


class TestMemoToolExecutorNewPath:
    """MemoToolExecutor: Resolver 注入時に being_id store に書く。"""

    def test_memo_add_は_being_id_store_に書く(
        self,
        memo_store: InMemoryMemoStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
        provisioning: BeingProvisioningService,
    ) -> None:
        """provisioning で Being を attach → memo_add は being_id 経路で書く。"""
        being_id = provisioning.ensure_attached(PlayerId(2))
        assert being_id == BeingId("being_w1_p2")

        executor = MemoToolExecutor(
            memo_store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        handlers = executor.get_handlers()
        result = handlers[TOOL_NAME_MEMO_ADD](2, {"content": "via being"})
        assert result.success is True

        # being store にデータが入っているはず (= 唯一の store、Step 3a-3 で legacy 撤去済)
        entries = memo_store.list_uncompleted_by_being(being_id)
        assert len(entries) == 1
        assert entries[0].content == "via being"

    def test_memo_list_は_being_id_store_から読む(
        self,
        memo_store: InMemoryMemoStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
        provisioning: BeingProvisioningService,
    ) -> None:
        """add した memo が memo_list で取れる。"""
        being_id = provisioning.ensure_attached(PlayerId(2))
        memo_store.add_by_being(being_id, "stored via being")

        executor = MemoToolExecutor(
            memo_store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        handlers = executor.get_handlers()
        result = handlers[TOOL_NAME_MEMO_LIST](2, {})
        assert result.success is True
        assert "stored via being" in result.message

    def test_memo_done_は_being_id_store_で完了する(
        self,
        memo_store: InMemoryMemoStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
        provisioning: BeingProvisioningService,
    ) -> None:
        """add → done で being store の memo が完了する。"""
        being_id = provisioning.ensure_attached(PlayerId(2))
        memo_id = memo_store.add_by_being(being_id, "to complete")

        executor = MemoToolExecutor(
            memo_store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        handlers = executor.get_handlers()
        result = handlers[TOOL_NAME_MEMO_DONE](2, {"memo_ids": [memo_id]})
        assert result.success is True
        # being store からは消えるが、旧 store は空のまま (= 独立性維持)
        assert memo_store.list_uncompleted_by_being(being_id) == []

    def test_provision_せず_Resolver_注入だけだと_RuntimeError_で_fail_fast(
        self,
        memo_store: InMemoryMemoStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
    ) -> None:
        """Phase 3 Step 3a-3: Resolver は注入されたが Being が provision されて
        いないと、exception_result でラップされた失敗結果が返る (= fail-fast)。
        legacy fallback はもうない。
        """
        executor = MemoToolExecutor(
            memo_store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        handlers = executor.get_handlers()
        result = handlers[TOOL_NAME_MEMO_ADD](2, {"content": "no being"})
        # exception_result で包まれた失敗 (= MemoToolExecutor 内 try/except)
        assert result.success is False


class TestMemoCompletionHintServiceNewPath:
    """MemoCompletionHintService: Resolver 注入時に being_id store から read。"""

    def test_detect_は_being_id_store_の_memo_を見る(
        self,
        memo_store: InMemoryMemoStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
        provisioning: BeingProvisioningService,
    ) -> None:
        """being store に memo を入れて、Resolver 経由で hint が引ける。"""
        being_id = provisioning.ensure_attached(PlayerId(2))
        memo_store.add_by_being(being_id, "りんごを採集する")

        service = MemoCompletionHintService(
            memo_store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            similarity_threshold=0.3,
        )
        hint = service.detect(
            PlayerId(2),
            action_summary="採集する",
            result_summary="りんごを 3 個入手しました",
        )
        assert hint is not None
        assert hint.memo.content == "りんごを採集する"


class _FetchUncompletedAdapter:
    """``DefaultPromptBuilder._fetch_uncompleted_memos`` の dual-path 分岐を
    最小依存で検査するためのアダプター。

    実際の ``DefaultPromptBuilder`` は多数の協調オブジェクトを要するので、
    本テストでは「_fetch_uncompleted_memos がどう memo_store / Resolver を
    使うか」のロジックだけを切り出して検証する (= MagicMock 直叩きより明示的)。
    本体側の helper 実装が変わったら本テストも追従が必要。
    """

    def __init__(
        self,
        memo_store: InMemoryMemoStore,
        resolver: BeingAttachmentResolver | None,
        world_id: WorldId | None,
    ) -> None:
        self._memo_store = memo_store
        self._being_attachment_resolver = resolver
        self._default_world_id = world_id

    # DefaultPromptBuilder._fetch_uncompleted_memos のロジックを再現
    def fetch(self, player_id: PlayerId):
        from ai_rpg_world.application.llm.services.prompt_builder import (
            DefaultPromptBuilder,
        )
        return DefaultPromptBuilder._fetch_uncompleted_memos(self, player_id)


class TestPromptBuilderNewPath:
    """DefaultPromptBuilder: Resolver 注入時の memo 取得経路。

    prompt_builder 本体は構築コストが大きいので、_fetch_uncompleted_memos
    helper を直接テストする (= dual-path 分岐の単体検証で十分)。
    """

    def test_fetch_uncompleted_memos_は_being_経路を使う(
        self,
        memo_store: InMemoryMemoStore,
        resolver: BeingAttachmentResolver,
        world_id: WorldId,
        provisioning: BeingProvisioningService,
    ) -> None:
        """attach 済 Being なら being_id 経路で取得される。"""
        being_id = provisioning.ensure_attached(PlayerId(2))
        memo_store.add_by_being(being_id, "via being")

        adapter = _FetchUncompletedAdapter(memo_store, resolver, world_id)
        entries = adapter.fetch(PlayerId(2))
        assert len(entries) == 1
        assert entries[0].content == "via being"
