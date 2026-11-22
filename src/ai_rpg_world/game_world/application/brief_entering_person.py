from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import Orientation
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.value_object import DescriptionText, PersonId


@final
@dataclass(frozen=True)
class BriefEnteringPersonCommand:
    person: PersonId
    known_facts: DescriptionText
    objective: DescriptionText


@final
@dataclass(frozen=True)
class EntryBriefing:
    orientation: Orientation
    imposed_goal: str
    known_people: tuple[PersonId, ...]


@final
class BriefEnteringPerson:
    def __init__(self, design: WorldDesign) -> None:
        self._design = design

    def __call__(self, command: BriefEnteringPersonCommand) -> EntryBriefing:
        character = self._design.nouns.character_of(command.person)
        return EntryBriefing(
            orientation=self._design.briefing_headings.orientation(self._design.introduction, command.known_facts),
            imposed_goal=command.objective.text,
            known_people=character.knows_at_start,
        )
