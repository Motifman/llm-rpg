from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.infrastructure.in_memory_being_repository import InMemoryBeingRepository
from ai_rpg_world.domain.being.exception.being_exceptions import BeingNotFoundException

GEN = BeingId("gen")


class TestInMemoryBeingRepository:
    """InMemoryBeingRepository が、いない Being を断り、もういる Being を足し直しても書き換えないことを保証する。"""

    def test_get_refuses_being_not_yet_saved(self) -> None:
        """まだ保存していない Being を get すると BeingNotFoundException を投げる。"""
        with pytest.raises(BeingNotFoundException):
            InMemoryBeingRepository().get(GEN)

    def test_add_if_absent_adds_new_being(self) -> None:
        """いない Being を add_if_absent すると、その人柄で get できる。"""
        beings = InMemoryBeingRepository()

        beings.add_if_absent(Being(GEN, Persona(name="ゲン")))

        assert beings.get(GEN).persona == Persona(name="ゲン")

    def test_add_if_absent_keeps_existing_being(self) -> None:
        """同じ BeingId の Being がもういると、add_if_absent しても人柄も入っている環境も変わらない。"""
        beings = InMemoryBeingRepository()
        attachment = BeingAttachment(environment_id="mine#1", environment_name="廃坑の山村")
        beings.save(Being(GEN, Persona(name="ゲン", first_person="わし"), attachment))

        beings.add_if_absent(Being(GEN, Persona(name="ゲン", first_person="俺")))

        kept = beings.get(GEN)
        assert (kept.persona.first_person, kept.attachment) == ("わし", attachment)

    def test_changes_after_get_are_not_saved_until_save(self) -> None:
        """get した Being を環境に入れても、save するまで保存先の Being は環境に入っていない。"""
        beings = InMemoryBeingRepository()
        beings.save(Being(GEN, Persona(name="ゲン")))

        beings.get(GEN).attach(BeingAttachment(environment_id="mine#1", environment_name="廃坑の山村"))

        assert beings.get(GEN).attachment is None
