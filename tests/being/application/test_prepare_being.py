from __future__ import annotations

import pytest

from ai_rpg_world.being.application.prepare_being import PrepareBeing, PrepareBeingCommand
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.infrastructure.in_memory_being_repository import InMemoryBeingRepository
from ai_rpg_world.domain.being.exception.being_exceptions import PersonaValidationException

GEN = BeingId("gen")


class TestPrepareBeing:
    """PrepareBeing が、シナリオの人柄の欄から Being を用意し、すでにいる Being の人柄は書き換えないことを保証する。"""

    def test_prepares_being_with_persona_from_fields(self) -> None:
        """人柄の欄 (名前「ゲン」、一人称「俺」、性格の一覧) を渡すと、その人柄で、どこにも入っていない Being が保存される。"""
        beings = InMemoryBeingRepository()

        PrepareBeing(beings).execute(
            PrepareBeingCommand(
                being_id=GEN,
                persona_fields={
                    "name": "ゲン",
                    "first_person": "俺",
                    "traits": ("口数は少ないが、坑道の空気には敏い",),
                },
            )
        )

        prepared = beings.find_by_id(GEN)
        assert prepared is not None
        assert prepared.persona == Persona(
            name="ゲン", first_person="俺", traits=("口数は少ないが、坑道の空気には敏い",)
        )
        assert prepared.attachment is None

    def test_existing_being_keeps_its_persona(self) -> None:
        """同じ BeingId の Being がもういれば、シナリオの人柄で書き換えず、もとの人柄のまま残る。"""
        beings = InMemoryBeingRepository()
        beings.save(Being(GEN, Persona(name="ゲン", first_person="わし")))

        PrepareBeing(beings).execute(
            PrepareBeingCommand(being_id=GEN, persona_fields={"name": "ゲン", "first_person": "俺"})
        )

        prepared = beings.find_by_id(GEN)
        assert prepared is not None
        assert prepared.persona.first_person == "わし"

    def test_unknown_field_is_refused_and_nothing_is_saved(self) -> None:
        """人柄に無い欄 (objective) が混ざると PersonaValidationException を投げ、Being は保存されない。"""
        beings = InMemoryBeingRepository()

        with pytest.raises(PersonaValidationException):
            PrepareBeing(beings).execute(
                PrepareBeingCommand(being_id=GEN, persona_fields={"name": "ゲン", "objective": "外へ出る"})
            )

        assert beings.find_by_id(GEN) is None

    def test_unknown_field_is_refused_even_for_existing_being(self) -> None:
        """同じ BeingId の Being がもういても、人柄に無い欄があれば PersonaValidationException を投げ、シナリオの誤りを見逃さない。"""
        beings = InMemoryBeingRepository()
        beings.save(Being(GEN, Persona(name="ゲン")))

        with pytest.raises(PersonaValidationException):
            PrepareBeing(beings).execute(
                PrepareBeingCommand(being_id=GEN, persona_fields={"name": "ゲン", "objective": "外へ出る"})
            )
