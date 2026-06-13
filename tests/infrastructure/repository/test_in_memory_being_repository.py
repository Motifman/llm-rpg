"""InMemoryBeingRepository の永続化挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


def _being(
    value: str = "ada",
    name: str = "アダ",
    *,
    attached: tuple[int, int] | None = None,
) -> Being:
    attachment = (
        BeingAttachment(world_id=WorldId(attached[0]), player_id=PlayerId(attached[1]))
        if attached is not None
        else None
    )
    return Being(
        being_id=BeingId(value),
        identity=BeingIdentity(name=name, first_person="わたし"),
        attachment=attachment,
    )


class TestInMemoryBeingRepository:
    """InMemoryBeingRepository の CRUD 挙動。"""

    def test_save_して_find_by_id_で取り出せる(self) -> None:
        """save 後に同じ ID で find すると同一 Being が返る。"""
        repo = InMemoryBeingRepository()
        being = _being("ada")
        repo.save(being)
        found = repo.find_by_id(BeingId("ada"))
        assert found is being

    def test_存在しない_ID_の_find_by_id_は_None(self) -> None:
        """未保存の ID では None が返る。"""
        repo = InMemoryBeingRepository()
        assert repo.find_by_id(BeingId("missing")) is None

    def test_save_は同一_ID_を上書きする(self) -> None:
        """同じ BeingId で save し直すと値が更新される (upsert)。"""
        repo = InMemoryBeingRepository()
        repo.save(_being("ada", name="アダ"))
        repo.save(_being("ada", name="アダ2"))
        found = repo.find_by_id(BeingId("ada"))
        assert found is not None
        assert found.identity.name == "アダ2"

    def test_exists_は保存後_True_を返す(self) -> None:
        """save 済みなら exists が True。"""
        repo = InMemoryBeingRepository()
        repo.save(_being("ada"))
        assert repo.exists(BeingId("ada")) is True
        assert repo.exists(BeingId("missing")) is False

    def test_delete_は存在すれば_True_削除後は_find_できない(self) -> None:
        """delete は存在時 True を返し、以降 find は None。"""
        repo = InMemoryBeingRepository()
        repo.save(_being("ada"))
        assert repo.delete(BeingId("ada")) is True
        assert repo.find_by_id(BeingId("ada")) is None

    def test_delete_は存在しなければ_False(self) -> None:
        """未保存の ID への delete は False。"""
        repo = InMemoryBeingRepository()
        assert repo.delete(BeingId("missing")) is False

    def test_save_に非_Being_を渡すと_TypeError(self) -> None:
        """型違反は TypeError として弾く。"""
        repo = InMemoryBeingRepository()
        with pytest.raises(TypeError):
            repo.save("not-a-being")  # type: ignore[arg-type]

    def test_find_by_id_に非_BeingId_を渡すと_TypeError(self) -> None:
        """型違反は TypeError として弾く。"""
        repo = InMemoryBeingRepository()
        with pytest.raises(TypeError):
            repo.find_by_id("ada")  # type: ignore[arg-type]


class TestInMemoryBeingRepositoryFindAllAttachedTo:
    """find_all_attached_to の挙動 (= Phase 3 Step 2 で追加)。"""

    def test_attach_中の_Being_が_1_件マッチする(self) -> None:
        """正常系: ある (world, player) に attach 中の Being を 1 件返す。"""
        repo = InMemoryBeingRepository()
        repo.save(_being("ada", attached=(1, 2)))
        result = repo.find_all_attached_to(WorldId(1), PlayerId(2))
        assert len(result) == 1
        assert result[0].being_id == BeingId("ada")

    def test_未_attach_の_Being_はヒットしない(self) -> None:
        """detach 中の Being は (world, player) 検索の対象外。"""
        repo = InMemoryBeingRepository()
        repo.save(_being("ada", attached=None))
        assert repo.find_all_attached_to(WorldId(1), PlayerId(2)) == []

    def test_別世界の_Being_はヒットしない(self) -> None:
        """world_id が違えばマッチしない。"""
        repo = InMemoryBeingRepository()
        repo.save(_being("ada", attached=(2, 2)))
        assert repo.find_all_attached_to(WorldId(1), PlayerId(2)) == []

    def test_同_world_player_に_複数の_Being_があれば_全件返す(self) -> None:
        """異常状態の検出は Resolver 側に委ねるため、本 method は単に全件返す。"""
        repo = InMemoryBeingRepository()
        repo.save(_being("ada", attached=(1, 2)))
        repo.save(_being("ben", attached=(1, 2)))
        result = repo.find_all_attached_to(WorldId(1), PlayerId(2))
        assert {b.being_id.value for b in result} == {"ada", "ben"}

    def test_非_VO_を渡すと_TypeError(self) -> None:
        """型違反は TypeError で弾く。"""
        repo = InMemoryBeingRepository()
        with pytest.raises(TypeError, match="world_id"):
            repo.find_all_attached_to(1, PlayerId(2))  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="player_id"):
            repo.find_all_attached_to(WorldId(1), 2)  # type: ignore[arg-type]
