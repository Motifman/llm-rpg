from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.game_world.application.person.place_departed_person import (
    PlaceDepartedPerson,
    PlaceDepartedPersonCommand,
)
from ai_rpg_world.game_world.domain.person import PersonDiedEvent


@final
class PlaceDepartedPersonHandler(EventHandler[PersonDiedEvent]):
    def __init__(self, place_departed_person: PlaceDepartedPerson) -> None:
        self._place_departed_person = place_departed_person

    def handle(self, event: PersonDiedEvent) -> None:
        self._place_departed_person(PlaceDepartedPersonCommand(event.person))
