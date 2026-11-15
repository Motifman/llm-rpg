from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.game_world.application.deliver_surroundings import DeliverSurroundings, DeliverSurroundingsCommand
from ai_rpg_world.game_world.domain.whereabouts import OccupantEnteredSpotEvent


@final
class DeliverSurroundingsOnArrivalHandler(EventHandler[OccupantEnteredSpotEvent]):
    def __init__(self, deliver_surroundings: DeliverSurroundings) -> None:
        self._deliver_surroundings = deliver_surroundings

    def handle(self, event: OccupantEnteredSpotEvent) -> None:
        self._deliver_surroundings(DeliverSurroundingsCommand(person=event.occupant.person, at=event.at))
