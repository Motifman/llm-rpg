from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import AggregateRoot, new_event_stamp
from ai_rpg_world.game_world.domain.declaration.object_and_item.object_declaration import ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.spot import NoCapacity, SpotDeclaration, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.exception.game_world_exception import require_distinct_memento_keys
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import (
    OccupantAlreadyInSectionException,
    OccupantAlreadyPlacedException,
    OccupantNotAtRouteStartException,
    OccupantNotAtSectionSpotException,
    OccupantNotInSectionException,
    OccupantNotPlacedException,
    OccupantNotTravellingException,
    SectionFullException,
)
from ai_rpg_world.game_world.domain.value_object import PassageId, PersonId, SpotId, Ticks, WorldId
from ai_rpg_world.game_world.domain.whereabouts.location import (
    AtSpot,
    Location,
    OpenArea,
    TravelInProgress,
    TravelPosition,
)
from ai_rpg_world.game_world.domain.whereabouts.occupant import DepartedPerson, Occupant
from ai_rpg_world.game_world.domain.whereabouts.route import Route
from ai_rpg_world.game_world.domain.whereabouts.whereabouts_events import (
    OccupantEnteredSectionEvent,
    OccupantEnteredSpotEvent,
    OccupantLeftSectionEvent,
    OccupantLeftSpotEvent,
    OccupantPlacedEvent,
    OccupantRemovedEvent,
    OccupantTeleportedEvent,
    TravelBlockedEvent,
    TravelCancelledEvent,
    TravelStartedEvent,
    WhereaboutsEvent,
)

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class OccupantLocation:
    occupant: Occupant
    location: AtSpot | TravelPosition


@final
@dataclass(frozen=True)
class WhereaboutsMemento:
    world_id: WorldId
    locations: frozenset[OccupantLocation]

    def __post_init__(self) -> None:
        require_distinct_memento_keys(
            [entry.occupant for entry in self.locations],
            f"world {self.world_id.value} has an occupant at two locations",
        )


class Whereabouts(AggregateRoot[WhereaboutsEvent]):
    def __init__(self, world_id: WorldId, locations: Mapping[Occupant, Location]) -> None:
        super().__init__()
        self._world_id = world_id
        self._locations = dict(locations)

    @classmethod
    def start(cls, world_id: WorldId) -> Whereabouts:
        return cls(world_id, {})

    @classmethod
    def from_memento(cls, memento: WhereaboutsMemento, design: WorldDesign) -> Whereabouts:
        return cls(memento.world_id, {entry.occupant: _resumed(entry.location, design) for entry in memento.locations})

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def memento(self) -> WhereaboutsMemento:
        return WhereaboutsMemento(
            world_id=self._world_id,
            locations=frozenset(
                OccupantLocation(occupant, location.position() if isinstance(location, TravelInProgress) else location)
                for occupant, location in self._locations.items()
            ),
        )

    def place(self, occupant: Occupant, spot: SpotDeclaration) -> None:
        if occupant in self._locations:
            raise OccupantAlreadyPlacedException(f"{occupant} is already in {self._world_id.value}")
        self._locations[occupant] = AtSpot(spot=spot.spot_id, section=OpenArea())
        self.add_event(
            OccupantPlacedEvent(**new_event_stamp(), world_id=self._world_id, occupant=occupant, spot=spot.spot_id)
        )

    def remove(self, occupant: Occupant) -> None:
        last_location = self.location_of(occupant)
        del self._locations[occupant]
        self.add_event(
            OccupantRemovedEvent(
                **new_event_stamp(), world_id=self._world_id, occupant=occupant, last_location=last_location
            )
        )

    def start_travel(self, occupant: Occupant, route: Route) -> None:
        location = self._locations.get(occupant)
        if not isinstance(location, AtSpot) or location.spot != route.start:
            raise OccupantNotAtRouteStartException(f"{occupant} is not at {route.start.value!r}")
        self._leave_section_if_inside(occupant, location)
        self._locations[occupant] = TravelInProgress(
            route=route,
            passage_index=0,
            ticks_left_on_passage=route.passages[0].travel_ticks,
            departed_from=route.start,
        )
        self.add_event(TravelStartedEvent(**new_event_stamp(), world_id=self._world_id, occupant=occupant, route=route))
        self.add_event(
            OccupantLeftSpotEvent(**new_event_stamp(), world_id=self._world_id, occupant=occupant, spot=route.start)
        )

    def advance_travels(self, closed_passages: frozenset[PassageId]) -> None:
        for occupant, location in list(self._locations.items()):
            if isinstance(location, TravelInProgress):
                self._advance(occupant, location, closed_passages)

    def cancel_travel(self, occupant: Occupant) -> None:
        location = self._locations.get(occupant)
        if not isinstance(location, TravelInProgress):
            raise OccupantNotTravellingException(f"{occupant} is not travelling")
        self._stop_at(occupant, location.departed_from)
        self.add_event(
            TravelCancelledEvent(
                **new_event_stamp(), world_id=self._world_id, occupant=occupant, returned_to=location.departed_from
            )
        )
        self._announce_arrival(occupant, location.departed_from)

    def teleport(self, occupant: Occupant, spot: SpotDeclaration) -> None:
        before = self.location_of(occupant)
        if isinstance(before, AtSpot):
            self._leave_section_if_inside(occupant, before)
        self._stop_at(occupant, spot.spot_id)
        self.add_event(
            OccupantTeleportedEvent(
                **new_event_stamp(), world_id=self._world_id, occupant=occupant, before=before, after=spot.spot_id
            )
        )
        self._announce_arrival(occupant, spot.spot_id)

    def enter_section(
        self, occupant: Occupant, section: SpotSectionDeclaration, not_counted: frozenset[PersonId]
    ) -> None:
        location = self._locations.get(occupant)
        if not isinstance(location, AtSpot) or location.spot != section.spot_id:
            raise OccupantNotAtSectionSpotException(f"{occupant} is not at {section.spot_id.value!r}")
        if location.section == section.section_id:
            raise OccupantAlreadyInSectionException(f"{occupant} is already in {section.section_id.value}")
        if self._is_full(section, not_counted):
            raise SectionFullException(f"{section.section_id.value} has no room for {occupant}")
        self._leave_section_if_inside(occupant, location)
        self._locations[occupant] = AtSpot(spot=section.spot_id, section=section.section_id)
        self.add_event(
            OccupantEnteredSectionEvent(
                **new_event_stamp(), world_id=self._world_id, occupant=occupant, section=section.section_id
            )
        )

    def leave_section(self, occupant: Occupant) -> None:
        location = self._locations.get(occupant)
        if not isinstance(location, AtSpot) or isinstance(location.section, OpenArea):
            raise OccupantNotInSectionException(f"{occupant} is not in any section")
        self._leave_section_if_inside(occupant, location)

    def location_of(self, occupant: Occupant) -> Location:
        if occupant not in self._locations:
            raise OccupantNotPlacedException(f"{occupant} is not in {self._world_id.value}")
        return self._locations[occupant]

    def occupants_at(self, spot: SpotDeclaration) -> tuple[Occupant, ...]:
        return tuple(occupant for occupant in self._locations if self._spot_of(occupant) == spot.spot_id)

    def are_together(self, actor: Occupant, target: Occupant) -> bool:
        here = self._spot_of(actor)
        return here is not None and here == self._spot_of(target)

    def is_at(self, occupant: Occupant, spot: SpotDeclaration) -> bool:
        return self._spot_of(occupant) == spot.spot_id

    def is_in_section(self, occupant: Occupant, section: SpotSectionDeclaration) -> bool:
        return self._locations.get(occupant) == AtSpot(spot=section.spot_id, section=section.section_id)

    def can_reach(
        self, occupant: Occupant, obj: ObjectDeclaration, sections: tuple[SpotSectionDeclaration, ...]
    ) -> bool:
        enclosing = [section for section in sections if obj.object_id in section.reachable_objects]
        if enclosing:
            return any(self.is_in_section(occupant, section) for section in enclosing)
        return self._spot_of(occupant) == obj.spot_id

    def _advance(self, occupant: Occupant, travel: TravelInProgress, closed_passages: frozenset[PassageId]) -> None:
        route = travel.route
        passage_index = travel.passage_index
        ticks_left = travel.ticks_left_on_passage.value
        departed_from = travel.departed_from
        spare = 1
        while True:
            passage_id = route.passages[passage_index].passage_id
            if passage_id in closed_passages:
                self._stop_at(occupant, departed_from)
                self.add_event(
                    TravelBlockedEvent(
                        **new_event_stamp(),
                        world_id=self._world_id,
                        occupant=occupant,
                        passage=passage_id,
                        stopped_at=departed_from,
                    )
                )
                self._announce_arrival(occupant, departed_from)
                return
            if ticks_left > spare:
                self._locations[occupant] = TravelInProgress(
                    route=route,
                    passage_index=passage_index,
                    ticks_left_on_passage=Ticks(ticks_left - spare),
                    departed_from=departed_from,
                )
                return
            spare -= ticks_left
            departed_from = route.end_of_passage(passage_index)
            if passage_index + 1 == len(route.passages):
                self._stop_at(occupant, departed_from)
                self._announce_arrival(occupant, departed_from)
                return
            passage_index += 1
            ticks_left = route.passages[passage_index].travel_ticks.value

    def _is_full(self, section: SpotSectionDeclaration, not_counted: frozenset[PersonId]) -> bool:
        if isinstance(section.capacity, NoCapacity):
            return False
        inside = AtSpot(spot=section.spot_id, section=section.section_id)
        counted = sum(
            1
            for occupant, location in self._locations.items()
            if location == inside and (isinstance(occupant, DepartedPerson) or occupant.person not in not_counted)
        )
        return counted >= section.capacity.value

    def _leave_section_if_inside(self, occupant: Occupant, location: AtSpot) -> None:
        if isinstance(location.section, OpenArea):
            return
        self._locations[occupant] = AtSpot(spot=location.spot, section=OpenArea())
        self.add_event(
            OccupantLeftSectionEvent(
                **new_event_stamp(), world_id=self._world_id, occupant=occupant, section=location.section
            )
        )

    def _stop_at(self, occupant: Occupant, spot: SpotId) -> None:
        self._locations[occupant] = AtSpot(spot=spot, section=OpenArea())

    def _announce_arrival(self, occupant: Occupant, spot: SpotId) -> None:
        self.add_event(
            OccupantEnteredSpotEvent(**new_event_stamp(), world_id=self._world_id, occupant=occupant, spot=spot)
        )

    def _spot_of(self, occupant: Occupant) -> SpotId | None:
        location = self._locations.get(occupant)
        return location.spot if isinstance(location, AtSpot) else None


def _resumed(location: AtSpot | TravelPosition, design: WorldDesign) -> Location:
    if isinstance(location, AtSpot):
        design.nouns.spot_of(location.spot)
        if not isinstance(location.section, OpenArea):
            section = design.nouns.section_of(location.section)
            if section.spot_id != location.spot:
                raise OccupantNotAtSectionSpotException(
                    f"{location.section.value} is in {section.spot_id.value!r}, not {location.spot.value!r}"
                )
        return location
    design.nouns.spot_of(location.departed_from)
    return location.resumed_on(tuple(design.nouns.passage_of(passage) for passage in location.route_passages))
