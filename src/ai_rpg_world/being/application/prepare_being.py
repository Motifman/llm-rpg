from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.being_repository import BeingRepository
from ai_rpg_world.being.domain.persona import Persona


@dataclass(frozen=True)
class PrepareBeingCommand:
    being_id: BeingId
    persona_fields: Mapping[str, object]


class PrepareBeing:
    def __init__(self, beings: BeingRepository) -> None:
        self._beings = beings

    def execute(self, command: PrepareBeingCommand) -> None:
        self._beings.add_if_absent(Being(command.being_id, Persona.from_fields(command.persona_fields)))


__all__ = ["PrepareBeing", "PrepareBeingCommand"]
