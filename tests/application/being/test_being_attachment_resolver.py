"""BeingAttachmentResolver が、ゲームの側の対応表 (PlayerBeings) からプレイヤーと Being を引き合うことを保証する (design_decisions D1928)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.being.being_attachment_resolver import BeingAttachmentResolver
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.aggregate.player_beings import PlayerBeings
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import InMemoryBeingRepository


def _being(being_id: str, *, attached: tuple[int, int] | None = None) -> Being:
    attachment = (
        BeingAttachment(environment_id=f"w{attached[0]}p{attached[1]}", environment_name="廃坑の山村")
        if attached is not None
        else None
    )
    return Being(being_id=BeingId(being_id), persona=Persona(name="アダ"), attachment=attachment)


@pytest.fixture
def repo() -> InMemoryBeingRepository:
    return InMemoryBeingRepository()


@pytest.fixture
def player_beings() -> PlayerBeings:
    return PlayerBeings(WorldId(1))


@pytest.fixture
def resolver(repo: InMemoryBeingRepository, player_beings: PlayerBeings) -> BeingAttachmentResolver:
    return BeingAttachmentResolver(repo, player_beings)


class TestResolverConstruction:
    """コンストラクタの型ガードを保証する。"""

    def test_non_repository_raises_type_error(self, player_beings: PlayerBeings) -> None:
        """保存先でない値を渡すと TypeError を投げる。"""
        with pytest.raises(TypeError, match="being_repository"):
            BeingAttachmentResolver("not-a-repo", player_beings)  # type: ignore[arg-type]

    def test_non_player_beings_raises_type_error(self, repo: InMemoryBeingRepository) -> None:
        """対応表でない値を渡すと TypeError を投げる。"""
        with pytest.raises(TypeError, match="player_beings"):
            BeingAttachmentResolver(repo, "not-a-table")  # type: ignore[arg-type]


class TestResolveFromThePlayer:
    """プレイヤーから、それを動かす Being を引くことを保証する。"""

    def test_being_driving_the_player_is_returned(
        self, repo: InMemoryBeingRepository, player_beings: PlayerBeings, resolver: BeingAttachmentResolver
    ) -> None:
        """対応表でプレイヤーを動かしている Being の ID と、保存先の Being が返る。"""
        repo.save(_being("ada", attached=(1, 2)))
        player_beings.drive(PlayerId(2), BeingId("ada"))

        assert resolver.resolve_being_id(WorldId(1), PlayerId(2)) == BeingId("ada")
        being = resolver.resolve_attached_being(WorldId(1), PlayerId(2))
        assert being is not None and being.being_id == BeingId("ada")

    def test_being_attached_only_in_the_repository_is_not_found(
        self, repo: InMemoryBeingRepository, resolver: BeingAttachmentResolver
    ) -> None:
        """保存先の Being が所属を持っていても、対応表に無ければ引かない。保存先を番号で探さない。"""
        repo.save(_being("ada", attached=(1, 2)))

        assert resolver.resolve_being_id(WorldId(1), PlayerId(2)) is None
        assert resolver.resolve_attached_being(WorldId(1), PlayerId(2)) is None

    def test_other_world_has_no_being(self, player_beings: PlayerBeings, resolver: BeingAttachmentResolver) -> None:
        """対応表の世界と違う世界を尋ねると、動かす Being はいない。"""
        player_beings.drive(PlayerId(2), BeingId("ada"))

        assert resolver.resolve_being_id(WorldId(2), PlayerId(2)) is None

    def test_being_missing_from_the_repository_is_none(
        self, player_beings: PlayerBeings, resolver: BeingAttachmentResolver
    ) -> None:
        """対応表に載っていても保存先に無い Being は、resolve_attached_being で None になる。"""
        player_beings.drive(PlayerId(2), BeingId("ada"))

        assert resolver.resolve_attached_being(WorldId(1), PlayerId(2)) is None

    def test_wrong_types_raise_type_error(self, resolver: BeingAttachmentResolver) -> None:
        """世界やプレイヤーの型が違うと TypeError を投げる。"""
        with pytest.raises(TypeError, match="world_id"):
            resolver.resolve_being_id(1, PlayerId(2))  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="player_id"):
            resolver.resolve_being_id(WorldId(1), 2)  # type: ignore[arg-type]


class TestResolveFromTheBeing:
    """Being から、それが動かすプレイヤーを引くことを保証する。"""

    def test_player_driven_by_the_being_is_returned(
        self, player_beings: PlayerBeings, resolver: BeingAttachmentResolver
    ) -> None:
        """対応表で Being が動かしているプレイヤーが返る。"""
        player_beings.drive(PlayerId(2), BeingId("ada"))

        assert resolver.resolve_player_id(BeingId("ada")) == PlayerId(2)

    def test_being_driving_no_player_is_none(self, resolver: BeingAttachmentResolver) -> None:
        """どのプレイヤーも動かしていない Being は None。"""
        assert resolver.resolve_player_id(BeingId("ada")) is None

    def test_wrong_type_raises_type_error(self, resolver: BeingAttachmentResolver) -> None:
        """Being の ID の型が違うと TypeError を投げる。"""
        with pytest.raises(TypeError, match="being_id"):
            resolver.resolve_player_id("ada")  # type: ignore[arg-type]
