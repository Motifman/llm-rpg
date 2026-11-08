from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.character import GroupDeclaration
from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration, WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoWeather, WeatherState
from ai_rpg_world.game_world.domain.value_object import Capacity, HitPoints, PersonId


@final
@dataclass(frozen=True)
class StartingPerson:
    person: PersonId
    spawn_spot: SpotDeclaration
    items: tuple[ItemSpecDeclaration, ...]
    held: tuple[ItemSpecDeclaration, ...]
    groups: tuple[GroupDeclaration, ...]
    knows: tuple[PersonId, ...]
    hp: HitPoints
    pack_capacity: Capacity


@final
@dataclass(frozen=True)
class InitialWorld:
    people: tuple[StartingPerson, ...]
    raised_flags: frozenset[FlagDeclaration]
    stage: WorldStageDeclaration | NoWorldStages
    weather: WeatherState | NoWeather
