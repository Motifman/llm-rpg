"""InMemoryBeingRepository の永続化挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
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
        BeingAttachment(environment_id=f"w{attached[0]}p{attached[1]}", environment_name="廃坑の山村")
        if attached is not None
        else None
    )
    return Being(
        being_id=BeingId(value),
        persona=Persona(name=name, first_person="わたし"),
        attachment=attachment,
    )


class TestInMemoryBeingRepository:
    """InMemoryBeingRepository の CRUD 挙動。"""

    def test_save_find_id(self) -> None:
        """save 後に同じ ID で find すると等価な Being が返る (= snapshot 経由で再構築)。"""
        repo = InMemoryBeingRepository()
        being = _being("ada")
        repo.save(being)
        found = repo.find_by_id(BeingId("ada"))
        # Phase 4 Step 4-3: 内部 store が snapshot keyed になったため、codec
        # で再 decode した別 instance が返る。Being aggregate に ``__eq__`` は
        # ないので属性ごとに比較する。
        assert found is not None
        assert found.being_id == being.being_id
        assert found.persona == being.persona
        assert found.attachment == being.attachment

    def test_id_find_id_none(self) -> None:
        """未保存の ID では None が返る。"""
        repo = InMemoryBeingRepository()
        assert repo.find_by_id(BeingId("missing")) is None

    def test_save_same_id_overwrites(self) -> None:
        """同じ BeingId で save し直すと値が更新される (upsert)。"""
        repo = InMemoryBeingRepository()
        repo.save(_being("ada", name="アダ"))
        repo.save(_being("ada", name="アダ2"))
        found = repo.find_by_id(BeingId("ada"))
        assert found is not None
        assert found.persona.name == "アダ2"

    def test_returns_exists_after_true(self) -> None:
        """save 済みなら exists が True。"""
        repo = InMemoryBeingRepository()
        repo.save(_being("ada"))
        assert repo.exists(BeingId("ada")) is True
        assert repo.exists(BeingId("missing")) is False

    def test_delete_true_after_find(self) -> None:
        """delete は存在時 True を返し、以降 find は None。"""
        repo = InMemoryBeingRepository()
        repo.save(_being("ada"))
        assert repo.delete(BeingId("ada")) is True
        assert repo.find_by_id(BeingId("ada")) is None

    def test_delete_false(self) -> None:
        """未保存の ID への delete は False。"""
        repo = InMemoryBeingRepository()
        assert repo.delete(BeingId("missing")) is False

    def test_save_being_raises_type_error(self) -> None:
        """型違反は TypeError として弾く。"""
        repo = InMemoryBeingRepository()
        with pytest.raises(TypeError):
            repo.save("not-a-being")  # type: ignore[arg-type]

    def test_find_by_id_being_id_raises_type_error(self) -> None:
        """型違反は TypeError として弾く。"""
        repo = InMemoryBeingRepository()
        with pytest.raises(TypeError):
            repo.find_by_id("ada")  # type: ignore[arg-type]
