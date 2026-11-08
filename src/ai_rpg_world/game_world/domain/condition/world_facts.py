from __future__ import annotations

from typing import Protocol

from ai_rpg_world.game_world.domain.condition.chance_occasion import ChanceOccasion
from ai_rpg_world.game_world.domain.declaration.character.group_declaration import GroupDeclaration
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemSpecDeclaration,
    ObjectStateKeyDeclaration,
    StateValue,
)
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoDayNight, NoWeather, TimeOfDay, WeatherState
from ai_rpg_world.game_world.domain.person import LifeState, Outcome, Undecided
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    FatigueAmount,
    Gold,
    HungerAmount,
    PersonId,
    SpotId,
    Ticks,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import Occupant, TravelInProgress


class WorldFacts(Protocol):
    def now(self) -> WorldTick: ...

    def world_stage(self) -> WorldStageDeclaration | NoWorldStages: ...

    def ticks_in_world_stage(self) -> Ticks: ...

    def time_of_day(self) -> TimeOfDay | NoDayNight: ...

    def weather(self) -> WeatherState | NoWeather: ...

    def object_value(self, key: ObjectStateKeyDeclaration) -> StateValue: ...

    def item_count(self, person: PersonId, item_spec: ItemSpecDeclaration) -> Count: ...

    def is_holding(self, person: PersonId, item_spec: ItemSpecDeclaration) -> bool: ...

    def spot_of(self, occupant: Occupant) -> SpotId | TravelInProgress: ...

    def is_member(self, person: PersonId, group: GroupDeclaration) -> bool: ...

    def gold_of(self, person: PersonId) -> Gold: ...

    def hunger_of(self, person: PersonId) -> HungerAmount: ...

    def fatigue_of(self, person: PersonId) -> FatigueAmount: ...

    def life_state(self, person: PersonId) -> LifeState: ...

    def outcome_of(self, person: PersonId) -> Outcome | Undecided: ...

    def all_outcomes_decided(self) -> bool: ...

    def search_count(self, person: PersonId, spot: SpotId) -> Count: ...

    def people(self) -> tuple[PersonId, ...]: ...

    def roll(self, occasion: ChanceOccasion) -> float: ...
