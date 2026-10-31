"""BeingProvisioningService が、プレイヤーを動かす Being を用意し、ゲームの側の対応表に書くことを保証する (design_decisions D1928)。"""

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
from ai_rpg_world.domain.world.aggregate.player_beings import PlayerBeings
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


@pytest.fixture
def repo() -> InMemoryBeingRepository:
    return InMemoryBeingRepository()


ENVIRONMENT = BeingAttachment(environment_id="mine_village_v1#1", environment_name="廃坑の山村")


@pytest.fixture
def player_beings() -> PlayerBeings:
    return PlayerBeings(WorldId(1))


@pytest.fixture
def service(repo: InMemoryBeingRepository, player_beings: PlayerBeings) -> BeingProvisioningService:
    return BeingProvisioningService(repo, player_beings, ENVIRONMENT)


class TestConstruction:
    """コンストラクタの型ガードと、用意する世界を保証する。"""

    def test_world_is_the_world_of_the_table(self, repo: InMemoryBeingRepository) -> None:
        """用意する世界は、対応表の世界になる。"""
        assert BeingProvisioningService(repo, PlayerBeings(WorldId(7)), ENVIRONMENT).default_world_id == WorldId(7)

    def test_non_repository_raises_type_error(self, player_beings: PlayerBeings) -> None:
        """保存先でない値を渡すと TypeError を投げる。"""
        with pytest.raises(TypeError, match="being_repository"):
            BeingProvisioningService("not-a-repo", player_beings, ENVIRONMENT)  # type: ignore[arg-type]

    def test_non_environment_raises_type_error(
        self, repo: InMemoryBeingRepository, player_beings: PlayerBeings
    ) -> None:
        """環境でない値を渡すと TypeError を投げる。"""
        with pytest.raises(TypeError, match="environment"):
            BeingProvisioningService(repo, player_beings, "mine_village_v1#1")  # type: ignore[arg-type]

    def test_non_player_beings_raises_type_error(self, repo: InMemoryBeingRepository) -> None:
        """対応表でない値を渡すと TypeError を投げる。"""
        with pytest.raises(TypeError, match="player_beings"):
            BeingProvisioningService(repo, "not-a-table", ENVIRONMENT)  # type: ignore[arg-type]


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
        assert being.attachment == ENVIRONMENT

    def test_new_being_is_written_in_the_table(
        self, player_beings: PlayerBeings, service: BeingProvisioningService
    ) -> None:
        """新しく作った Being が、対応表でそのプレイヤーを動かす。"""
        being_id = service.ensure_attached(PlayerId(2))

        assert player_beings.being_of(PlayerId(2)) == being_id

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


class TestEnsureAttachedIdempotent:
    """idempotent な挙動: 既に attach 中なら何もしない。"""

    def test_player_already_driven_keeps_its_being(
        self, repo: InMemoryBeingRepository, player_beings: PlayerBeings, service: BeingProvisioningService
    ) -> None:
        """対応表でもう別の Being がプレイヤーを動かしていれば、その Being を返し、新しく作らない。"""
        player_beings.drive(PlayerId(2), BeingId("ada"))

        assert service.ensure_attached(PlayerId(2)) == BeingId("ada")
        assert repo.find_by_id(BeingId("being_w1_p2")) is None

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
            attachment=BeingAttachment(environment_id="other_world#1", environment_name="峠の野営地"),
        )
        repo.save(being)
        # ensure_attached(player_id=2) を呼ぶと既存 Being が player=2 に再 attach
        being_id = service.ensure_attached(PlayerId(2))
        assert being_id == BeingId("being_w1_p2")
        reloaded = repo.find_by_id(being_id)
        assert reloaded is not None
        assert reloaded.attachment is not None
        assert reloaded.attachment == ENVIRONMENT
        # identity は既存のものが残る (= 上書きしない)
        assert reloaded.persona.name == "既存"
        assert moved == [ENVIRONMENT]

    def test_moved_being_leaves_the_player_it_drove(
        self, repo: InMemoryBeingRepository, player_beings: PlayerBeings, service: BeingProvisioningService
    ) -> None:
        """同じ BeingId の Being が対応表でほかのプレイヤーを動かしていれば、そこを離れてこのプレイヤーを動かす。"""
        repo.save(
            Being(
                being_id=BeingId("being_w1_p2"),
                persona=Persona(name="既存"),
                attachment=BeingAttachment(environment_id="other_world#1", environment_name="峠の野営地"),
            )
        )
        player_beings.drive(PlayerId(99), BeingId("being_w1_p2"))

        service.ensure_attached(PlayerId(2))

        assert player_beings.being_of(PlayerId(2)) == BeingId("being_w1_p2")
        assert player_beings.being_of(PlayerId(99)) is None

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
        assert reloaded.attachment == ENVIRONMENT


class TestEnsureAttachedTypeGuards:
    """型違反の弾き方。"""

    def test_player_id_raises_type_error(self, service: BeingProvisioningService) -> None:
        """player_id の型違反は TypeError。"""
        with pytest.raises(TypeError, match="player_id"):
            service.ensure_attached(2)  # type: ignore[arg-type]

    def test_non_persona_raises_type_error(self, service: BeingProvisioningService) -> None:
        """persona に Persona でない値を渡すと TypeError を投げる。"""
        with pytest.raises(TypeError, match="persona"):
            service.ensure_attached(
                PlayerId(2),
                persona="アダ",  # type: ignore[arg-type]
            )
