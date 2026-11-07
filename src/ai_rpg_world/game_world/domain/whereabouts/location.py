from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object import SpotId, SpotSectionId, Ticks
from ai_rpg_world.game_world.domain.whereabouts.route import Route


@final
@dataclass(frozen=True)
class OpenArea:
    pass


@final
@dataclass(frozen=True)
class AtSpot:
    spot: SpotId
    section: SpotSectionId | OpenArea


@final
@dataclass(frozen=True)
class TravelInProgress:
    route: Route
    leg_index: int
    ticks_left_on_leg: Ticks
    departed_from: SpotId


Location = AtSpot | TravelInProgress
