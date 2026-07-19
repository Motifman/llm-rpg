"""BeingAttachmentResolver の双方向 ID 解決挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingMultipleAttachmentException,
)
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


def _identity() -> BeingIdentity:
    return BeingIdentity(name="アダ", first_person="わたし")


def _being(
    being_id: str = "ada",
    *,
    attached: tuple[int, int] | None = None,
) -> Being:
    attachment = (
        BeingAttachment(world_id=WorldId(attached[0]), player_id=PlayerId(attached[1]))
        if attached is not None
        else None
    )
    return Being(
        being_id=BeingId(being_id), identity=_identity(), attachment=attachment
    )


@pytest.fixture
def repo() -> InMemoryBeingRepository:
    return InMemoryBeingRepository()


@pytest.fixture
def resolver(repo: InMemoryBeingRepository) -> BeingAttachmentResolver:
    return BeingAttachmentResolver(repo)


class TestResolverConstruction:
    """コンストラクタの型ガード。"""

    def test_being_repository_can_create(
        self, repo: InMemoryBeingRepository
    ) -> None:
        """正しい Repository を渡せばインスタンス化される。"""
        BeingAttachmentResolver(repo)

    def test_being_repository_raises_type_error(self) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError, match="being_repository"):
            BeingAttachmentResolver("not-a-repo")  # type: ignore[arg-type]


class TestResolveAttachedBeing:
    """resolve_attached_being の挙動 (= (world, player) → Being | None)。"""

    def test_returns_being_attach_being(
        self,
        repo: InMemoryBeingRepository,
        resolver: BeingAttachmentResolver,
    ) -> None:
        """1 件マッチで唯一の Being が返る。"""
        repo.save(_being("ada", attached=(1, 2)))
        result = resolver.resolve_attached_being(WorldId(1), PlayerId(2))
        assert result is not None
        assert result.being_id == BeingId("ada")

    def test_returns_none_being(
        self,
        repo: InMemoryBeingRepository,
        resolver: BeingAttachmentResolver,
    ) -> None:
        """0 件マッチなら None。"""
        repo.save(_being("ada", attached=(1, 99)))  # 別 player
        assert resolver.resolve_attached_being(WorldId(1), PlayerId(2)) is None

    def test_attach_being_target_not_included(
        self,
        repo: InMemoryBeingRepository,
        resolver: BeingAttachmentResolver,
    ) -> None:
        """detach 中の Being は (world, player) 検索でヒットしない。"""
        repo.save(_being("ada", attached=None))
        assert resolver.resolve_attached_being(WorldId(1), PlayerId(2)) is None

    def test_different_world_player(
        self,
        repo: InMemoryBeingRepository,
        resolver: BeingAttachmentResolver,
    ) -> None:
        """world_id が違えば一致しない。"""
        repo.save(_being("ada", attached=(2, 2)))  # world=2
        assert resolver.resolve_attached_being(WorldId(1), PlayerId(2)) is None

    def test_world_player_two_being_attach_raises_exception(
        self,
        repo: InMemoryBeingRepository,
        resolver: BeingAttachmentResolver,
    ) -> None:
        """0..1 不変条件の破れは BeingMultipleAttachmentException。"""
        # aggregate ガードを迂回して直接 Repository に異常状態を作る
        repo.save(_being("ada", attached=(1, 2)))
        repo.save(_being("ben", attached=(1, 2)))
        with pytest.raises(
            BeingMultipleAttachmentException, match="multiple Beings"
        ):
            resolver.resolve_attached_being(WorldId(1), PlayerId(2))

    def test_vo_raises_type_error(
        self, resolver: BeingAttachmentResolver
    ) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError, match="world_id"):
            resolver.resolve_attached_being(1, PlayerId(2))  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="player_id"):
            resolver.resolve_attached_being(WorldId(1), 2)  # type: ignore[arg-type]


class TestResolveBeingId:
    """resolve_being_id の挙動 (= (world, player) → BeingId | None)。"""

    def test_returns_attach_being_id(
        self,
        repo: InMemoryBeingRepository,
        resolver: BeingAttachmentResolver,
    ) -> None:
        """attach Being の id が返る。"""
        repo.save(_being("ada", attached=(1, 2)))
        assert resolver.resolve_being_id(WorldId(1), PlayerId(2)) == BeingId(
            "ada"
        )

    def test_none(
        self,
        repo: InMemoryBeingRepository,
        resolver: BeingAttachmentResolver,
    ) -> None:
        """マッチしない (world, player) は None。"""
        assert resolver.resolve_being_id(WorldId(1), PlayerId(2)) is None


class TestResolvePlayerId:
    """resolve_player_id の挙動 (= BeingId → PlayerId | None)。"""

    def test_returns_attach_being_player_id(
        self,
        repo: InMemoryBeingRepository,
        resolver: BeingAttachmentResolver,
    ) -> None:
        """Being の attachment.player_id がそのまま返る。"""
        repo.save(_being("ada", attached=(1, 2)))
        assert resolver.resolve_player_id(BeingId("ada")) == PlayerId(2)

    def test_detach_being_none(
        self,
        repo: InMemoryBeingRepository,
        resolver: BeingAttachmentResolver,
    ) -> None:
        """attachment が None の Being は None を返す (= 例外ではない)。"""
        repo.save(_being("ada", attached=None))
        assert resolver.resolve_player_id(BeingId("ada")) is None

    def test_being_none(
        self, resolver: BeingAttachmentResolver
    ) -> None:
        """未保存の BeingId は None を返す (= 例外ではない)。"""
        assert resolver.resolve_player_id(BeingId("missing")) is None

    def test_being_id_raises_type_error(
        self, resolver: BeingAttachmentResolver
    ) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError, match="being_id"):
            resolver.resolve_player_id("ada")  # type: ignore[arg-type]
