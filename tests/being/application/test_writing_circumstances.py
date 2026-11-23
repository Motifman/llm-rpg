from __future__ import annotations

import pytest

from ai_rpg_world.being.application.handlers.write_episodes_handler import EpisodeWritingCircumstances
from ai_rpg_world.being.application.writing_circumstances import CircumstancesOfBeings
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.infrastructure.in_memory_being_repository import InMemoryBeingRepository

GEN = BeingId("gen")
GENS_PERSONA = Persona(name="ゲン", first_person="俺")
VILLAGE = BeingAttachment(environment_id="mine#1", environment_name="廃坑の山村", known_facts="坑道は暗い。")


def _beings(attachment: BeingAttachment | None) -> InMemoryBeingRepository:
    beings = InMemoryBeingRepository()
    beings.add_if_absent(Being(being_id=GEN, persona=GENS_PERSONA, attachment=attachment))
    return beings


class TestCircumstancesOfBeings:
    """CircumstancesOfBeings が、書き起こしに渡す人柄と人格の文と環境の名前を、Being の保存先だけから引くことを保証する。"""

    def test_persona_text_and_environment_come_from_the_being_itself(self) -> None:
        """廃坑の山村に入ったゲンは、【ペルソナ】と同じ文 (人柄とこの世界で知っていること) と、廃坑の山村の名前で書き起こす。"""
        circumstances = CircumstancesOfBeings(_beings(VILLAGE))

        assert circumstances.persona_of(GEN) == GENS_PERSONA
        assert circumstances.circumstances_of(GEN) == EpisodeWritingCircumstances(
            persona_text="あなたはゲン。\n\n坑道は暗い。\n\n一人称は「俺」。", environment_name="廃坑の山村"
        )
        assert circumstances.persona_text_of(GEN) == circumstances.circumstances_of(GEN).persona_text

    def test_being_outside_any_environment_is_refused(self) -> None:
        """どの環境にも入っていない Being は、書き起こす環境が無いので LookupError で断る。"""
        with pytest.raises(LookupError):
            CircumstancesOfBeings(_beings(None)).circumstances_of(GEN)
