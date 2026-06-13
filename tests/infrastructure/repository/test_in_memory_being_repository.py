"""InMemoryBeingRepository の永続化挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


def _being(value: str = "ada", name: str = "アダ") -> Being:
    return Being(
        being_id=BeingId(value),
        identity=BeingIdentity(name=name, first_person="わたし"),
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
