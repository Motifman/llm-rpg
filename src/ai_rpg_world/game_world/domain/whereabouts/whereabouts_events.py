from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.domain.value_object import PassageId, SpotId, SpotSectionId, WorldId
from ai_rpg_world.game_world.domain.whereabouts.location import Location
from ai_rpg_world.game_world.domain.whereabouts.occupant import Occupant
from ai_rpg_world.game_world.domain.whereabouts.route import Route


@final
@dataclass(frozen=True, kw_only=True)
class OccupantPlacedEvent(DomainEvent):
    world_id: WorldId
    occupant: Occupant
    spot: SpotId


@final
@dataclass(frozen=True, kw_only=True)
class OccupantRemovedEvent(DomainEvent):
    world_id: WorldId
    occupant: Occupant
    last_location: Location


@final
@dataclass(frozen=True, kw_only=True)
class TravelStartedEvent(DomainEvent):
    world_id: WorldId
    occupant: Occupant
    route: Route


@final
@dataclass(frozen=True, kw_only=True)
class OccupantLeftSpotEvent(DomainEvent):
    world_id: WorldId
    occupant: Occupant
    spot: SpotId


@final
@dataclass(frozen=True, kw_only=True)
class OccupantEnteredSpotEvent(DomainEvent):
    world_id: WorldId
    occupant: Occupant
    spot: SpotId


@final
@dataclass(frozen=True, kw_only=True)
class TravelBlockedEvent(DomainEvent):
    world_id: WorldId
    occupant: Occupant
    passage: PassageId
    stopped_at: SpotId


@final
@dataclass(frozen=True, kw_only=True)
class TravelCancelledEvent(DomainEvent):
    world_id: WorldId
    occupant: Occupant
    returned_to: SpotId


@final
@dataclass(frozen=True, kw_only=True)
class OccupantTeleportedEvent(DomainEvent):
    world_id: WorldId
    occupant: Occupant
    before: Location
    after: SpotId


@final
@dataclass(frozen=True, kw_only=True)
class OccupantEnteredSectionEvent(DomainEvent):
    world_id: WorldId
    occupant: Occupant
    section: SpotSectionId


@final
@dataclass(frozen=True, kw_only=True)
class OccupantLeftSectionEvent(DomainEvent):
    world_id: WorldId
    occupant: Occupant
    section: SpotSectionId


WhereaboutsEvent = (
    OccupantPlacedEvent
    | OccupantRemovedEvent
    | TravelStartedEvent
    | OccupantLeftSpotEvent
    | OccupantEnteredSpotEvent
    | TravelBlockedEvent
    | TravelCancelledEvent
    | OccupantTeleportedEvent
    | OccupantEnteredSectionEvent
    | OccupantLeftSectionEvent
)
