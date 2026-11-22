from __future__ import annotations

from dataclasses import fields

from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.game_world.infrastructure.scenario.noun_reader import PERSONA_FIELDS


def test_scenario_being_fields_are_the_persona_fields() -> None:
    """シナリオの being: が受け付ける欄の名前は、Persona の欄の名前と同じ並びで一致する。game_world は Persona を import できないので、境界の外で見張る (D2227)。"""
    assert PERSONA_FIELDS == tuple(field.name for field in fields(Persona))
