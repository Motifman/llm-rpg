"""BeingProvisioningService の idempotent な Being 確保挙動 (Phase 3 Step 6-mini)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
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

    def test_being_repository_can_build(self, repo: InMemoryBeingRepository) -> None:
        """正常系: Repository を渡せばインスタンス化される。"""
        s = BeingProvisioningService(repo)
        assert s.default_world_id == WorldId(1)

    def test_default_world_id_can_override(self, repo: InMemoryBeingRepository) -> None:
        """default_world_id を渡せばそれを使う。"""
        s = BeingProvisioningService(repo, default_world_id=WorldId(7))
        assert s.default_world_id == WorldId(7)

    def test_repository_raises_type_error(self) -> None:
        """型違反は TypeError。"""
        with pytest.raises(TypeError, match="being_repository"):
            BeingProvisioningService("not-a-repo")  # type: ignore[arg-type]

    def test_world_id_default_raises_type_error(self, repo: InMemoryBeingRepository) -> None:
        """default_world_id の型違反は TypeError。"""
        with pytest.raises(TypeError, match="default_world_id"):
            BeingProvisioningService(repo, default_world_id=1)  # type: ignore[arg-type]


class TestEnsureAttachedNewBeing:
    """初回 provisioning: Being が存在しないケース。"""

    def test_new_player_being_created(
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
        assert being.attachment == BeingAttachment(world_id=1, player_id=2)

    def test_persona_is_used_for_new_being(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """persona を渡すと、新しく作る Being がその人柄を持つ。"""
        hint = Persona(name="アダ", first_person="わたし")
        being_id = service.ensure_attached(PlayerId(2), persona=hint)
        being = repo.find_by_id(being_id)
        assert being is not None
        assert being.persona == hint

    def test_without_persona_only_placeholder_name_is_set(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """persona を渡さなければ、名前だけを ``agent_{player}`` にし、一人称などは決めない。"""
        being_id = service.ensure_attached(PlayerId(7))
        being = repo.find_by_id(being_id)
        assert being is not None
        assert being.persona == Persona(name="agent_7")

    def test_world_id_world_attach(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """world_id 指定で default を上書きできる。"""
        being_id = service.ensure_attached(PlayerId(3), world_id=WorldId(99))
        assert being_id == BeingId("being_w99_p3")
        being = repo.find_by_id(being_id)
        assert being is not None
        assert being.attachment is not None
        assert being.attachment.world_id == 99


class TestEnsureAttachedIdempotent:
    """idempotent な挙動: 既に attach 中なら何もしない。"""

    def test_returns_two_ensure_attached_same_being_id(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """同じ (world, player) で 2 回呼んでも同じ BeingId が返る。"""
        first = service.ensure_attached(PlayerId(2))
        second = service.ensure_attached(PlayerId(2))
        assert first == second

    def test_second_persona_does_not_overwrite_existing_persona(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """既にある Being の人柄は、2 回目に別の persona を渡しても変わらない。"""
        first_hint = Persona(name="アダ", first_person="わたし")
        service.ensure_attached(PlayerId(2), persona=first_hint)
        service.ensure_attached(
            PlayerId(2),
            persona=Persona(name="別人", first_person="俺"),
        )
        being = repo.find_by_id(BeingId("being_w1_p2"))
        assert being is not None
        assert being.persona == first_hint


class TestEnsureAttachedReattach:
    """同じ BeingId の Being が既にあるとき、Being.move_to でこの (world, player) に入れることを保証する。"""

    def test_creates_world_id_provisioning_independent_being(
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
        assert being_99.attachment.world_id == 99

        # 次に default world (= 1) で呼ぶ → 別 ID の新規 Being が作られる (= Case 3)
        new_being_id = service.ensure_attached(PlayerId(2))
        assert new_being_id == BeingId("being_w1_p2")
        assert new_being_id != being_id_99
        # 元の world=99 Being はそのまま attach 状態が維持される
        being_99_after = repo.find_by_id(being_id_99)
        assert being_99_after is not None
        assert being_99_after.is_attached is True

    def test_existing_being_attached_elsewhere_is_moved(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """同じ BeingId の Being が別の player に入っていれば、Being.move_to でこの player に移す。人柄は変えない。"""
        moved: list[BeingAttachment] = []
        original_move_to = Being.move_to

        def _spy(self: Being, attachment: BeingAttachment) -> None:
            moved.append(attachment)
            original_move_to(self, attachment)

        monkeypatch.setattr(Being, "move_to", _spy)
        # 事前に手動で Being を別 player に attach
        being = Being(
            being_id=BeingId("being_w1_p2"),
            persona=Persona(name="既存", first_person="わたし"),
            attachment=BeingAttachment(world_id=1, player_id=99),
        )
        repo.save(being)
        # ensure_attached(player_id=2) を呼ぶと既存 Being が player=2 に再 attach
        being_id = service.ensure_attached(PlayerId(2))
        assert being_id == BeingId("being_w1_p2")
        reloaded = repo.find_by_id(being_id)
        assert reloaded is not None
        assert reloaded.attachment is not None
        assert reloaded.attachment.player_id == 2
        # identity は既存のものが残る (= 上書きしない)
        assert reloaded.persona.name == "既存"
        assert moved == [BeingAttachment(world_id=1, player_id=2)]

    def test_existing_detached_being_is_moved_in(
        self,
        repo: InMemoryBeingRepository,
        service: BeingProvisioningService,
    ) -> None:
        """同じ BeingId の Being がどこにも入っていなければ、そのままこの player に入れる。"""
        repo.save(Being(being_id=BeingId("being_w1_p2"), persona=Persona(name="既存")))

        service.ensure_attached(PlayerId(2))

        reloaded = repo.find_by_id(BeingId("being_w1_p2"))
        assert reloaded is not None
        assert reloaded.attachment == BeingAttachment(world_id=1, player_id=2)


class TestEnsureAttachedTypeGuards:
    """型違反の弾き方。"""

    def test_player_id_raises_type_error(self, service: BeingProvisioningService) -> None:
        """player_id の型違反は TypeError。"""
        with pytest.raises(TypeError, match="player_id"):
            service.ensure_attached(2)  # type: ignore[arg-type]

    def test_world_id_world_id_raises_type_error(self, service: BeingProvisioningService) -> None:
        """world_id の型違反は TypeError。"""
        with pytest.raises(TypeError, match="world_id"):
            service.ensure_attached(PlayerId(2), world_id=1)  # type: ignore[arg-type]

    def test_non_persona_raises_type_error(self, service: BeingProvisioningService) -> None:
        """persona に Persona でない値を渡すと TypeError を投げる。"""
        with pytest.raises(TypeError, match="persona"):
            service.ensure_attached(
                PlayerId(2),
                persona="アダ",  # type: ignore[arg-type]
            )
