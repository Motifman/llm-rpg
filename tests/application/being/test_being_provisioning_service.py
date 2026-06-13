"""BeingProvisioningService の idempotent な Being 確保挙動 (Phase 3 Step 6-mini)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


@pytest.fixture
def repo() -> InMemoryBeingRepository:
    return InMemoryBeingRepository()


@pytest.fixture
def service(repo: InMemoryBeingRepository) -> BeingProvisioningService:
    return BeingProvisioningService(repo)


class TestConstruction:
    """コンストラクタの型ガード + default 値。"""

    def test_BeingRepository_を渡せば構築できる(
        self, repo: InMemoryBeingRepository
    ) -> None:
        """正常系: Repository を渡せばインスタンス化される。"""
        s = BeingProvisioningService(repo)
        assert s.default_world_id == WorldId(1)

    def test_default_world_id_を上書きできる(
        self, repo: InMemoryBeingRepository
    ) -> None:
        """default_world_id を渡せばそれを使う。"""
        s = BeingProvisioningService(repo, default_world_id=WorldId(7))
        assert s.default_world_id == WorldId(7)

    def test_非_Repository_は_TypeError(self) -> None:
        """型違反は TypeError。"""
        with pytest.raises(TypeError, match="being_repository"):
            BeingProvisioningService("not-a-repo")  # type: ignore[arg-type]

    def test_非_WorldId_の_default_は_TypeError(
        self, repo: InMemoryBeingRepository
    ) -> None:
        """default_world_id の型違反は TypeError。"""
        with pytest.raises(TypeError, match="default_world_id"):
            BeingProvisioningService(repo, default_world_id=1)  # type: ignore[arg-type]


class TestEnsureAttachedNewBeing:
    """初回 provisioning: Being が存在しないケース。"""

    def test_新規_player_に_Being_が作成される(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """初回呼び出しで決定論 ID の Being が作られ attach される。"""
        being_id = service.ensure_attached(PlayerId(2))
        assert being_id == BeingId("being_w1_p2")
        being = repo.find_by_id(being_id)
        assert being is not None
        assert being.is_attached is True
        assert being.attachment == BeingAttachment(
            world_id=WorldId(1), player_id=PlayerId(2)
        )

    def test_identity_hint_を渡せば反映される(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """identity_hint が新規 Being の identity に使われる。"""
        hint = BeingIdentity(name="アダ", first_person="わたし")
        being_id = service.ensure_attached(PlayerId(2), identity_hint=hint)
        being = repo.find_by_id(being_id)
        assert being is not None
        assert being.identity == hint

    def test_identity_hint_未指定なら_placeholder_が使われる(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """identity_hint が None なら ``agent_{player}`` 形式の placeholder。"""
        being_id = service.ensure_attached(PlayerId(7))
        being = repo.find_by_id(being_id)
        assert being is not None
        assert being.identity.name == "agent_7"
        assert being.identity.first_person == "わたし"

    def test_world_id_を渡せば_その_world_に_attach_される(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """world_id 指定で default を上書きできる。"""
        being_id = service.ensure_attached(
            PlayerId(3), world_id=WorldId(99)
        )
        assert being_id == BeingId("being_w99_p3")
        being = repo.find_by_id(being_id)
        assert being is not None
        assert being.attachment is not None
        assert being.attachment.world_id == WorldId(99)


class TestEnsureAttachedIdempotent:
    """idempotent な挙動: 既に attach 中なら何もしない。"""

    def test_2_回目の_ensure_attached_は同じ_BeingId_を返す(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """同じ (world, player) で 2 回呼んでも同じ BeingId が返る。"""
        first = service.ensure_attached(PlayerId(2))
        second = service.ensure_attached(PlayerId(2))
        assert first == second

    def test_2_回目で_identity_hint_を変えても_既存_identity_は変わらない(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """既存 Being の identity は idempotent 呼び出しで上書きされない。"""
        first_hint = BeingIdentity(name="アダ", first_person="わたし")
        service.ensure_attached(PlayerId(2), identity_hint=first_hint)
        # 2 回目に違う hint
        service.ensure_attached(
            PlayerId(2),
            identity_hint=BeingIdentity(name="別人", first_person="俺"),
        )
        being = repo.find_by_id(BeingId("being_w1_p2"))
        assert being is not None
        assert being.identity == first_hint


class TestEnsureAttachedReattach:
    """既存 Being が別 (world, player) に attach 中の場合、再 attach する。"""

    def test_異なる_world_id_での_provisioning_は_独立した_Being_を作る(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """同じ player_id でも world_id が違えば BeingId は別になる (= Case 3 新規作成)。

        決定論命名規約 ``being_w{world}_p{player}`` の確認。世界をまたぐと
        Being も別存在として扱う。
        """
        # 先に world=99 に attach
        service.ensure_attached(PlayerId(2), world_id=WorldId(99))
        being_id_99 = BeingId("being_w99_p2")
        being_99 = repo.find_by_id(being_id_99)
        assert being_99 is not None
        assert being_99.attachment is not None
        assert being_99.attachment.world_id == WorldId(99)

        # 次に default world (= 1) で呼ぶ → 別 ID の新規 Being が作られる (= Case 3)
        new_being_id = service.ensure_attached(PlayerId(2))
        assert new_being_id == BeingId("being_w1_p2")
        assert new_being_id != being_id_99
        # 元の world=99 Being はそのまま attach 状態が維持される
        being_99_after = repo.find_by_id(being_id_99)
        assert being_99_after is not None
        assert being_99_after.is_attached is True

    def test_既存_BeingId_を_別_player_に_引き継ぐと_detach_then_attach_される(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """事前に同 BeingId の Being が別 attach 状態で存在する場合、detach → attach。"""
        # 事前に手動で Being を別 player に attach
        being = Being(
            being_id=BeingId("being_w1_p2"),
            identity=BeingIdentity(name="既存", first_person="わたし"),
            attachment=BeingAttachment(
                world_id=WorldId(1), player_id=PlayerId(99)
            ),
        )
        repo.save(being)
        # ensure_attached(player_id=2) を呼ぶと既存 Being が player=2 に再 attach
        being_id = service.ensure_attached(PlayerId(2))
        assert being_id == BeingId("being_w1_p2")
        reloaded = repo.find_by_id(being_id)
        assert reloaded is not None
        assert reloaded.attachment is not None
        assert reloaded.attachment.player_id == PlayerId(2)
        # identity は既存のものが残る (= 上書きしない)
        assert reloaded.identity.name == "既存"


class TestEnsureAttachedTypeGuards:
    """型違反の弾き方。"""

    def test_非_PlayerId_は_TypeError(
        self, service: BeingProvisioningService
    ) -> None:
        """player_id の型違反は TypeError。"""
        with pytest.raises(TypeError, match="player_id"):
            service.ensure_attached(2)  # type: ignore[arg-type]

    def test_非_WorldId_の_world_id_は_TypeError(
        self, service: BeingProvisioningService
    ) -> None:
        """world_id の型違反は TypeError。"""
        with pytest.raises(TypeError, match="world_id"):
            service.ensure_attached(PlayerId(2), world_id=1)  # type: ignore[arg-type]

    def test_非_BeingIdentity_の_hint_は_TypeError(
        self, service: BeingProvisioningService
    ) -> None:
        """identity_hint の型違反は TypeError。"""
        with pytest.raises(TypeError, match="identity_hint"):
            service.ensure_attached(
                PlayerId(2), identity_hint="アダ"  # type: ignore[arg-type]
            )
