from __future__ import annotations

from typing import Protocol

from ai_rpg_world.game_world.domain.condition.aggregate_readings import (
    GroundItemsReading,
    GroupDecisionReading,
    GroupMembershipReading,
    ItemReading,
    ObjectStateReading,
    PassageStatesReading,
    PersonInventoryReading,
    PersonOutcomesReading,
    PersonVitalsReading,
    SpotAtmospheresReading,
    SpotSearchProgressReading,
    WeatherReading,
    WhereaboutsReading,
    WorldClockReading,
    WorldStageReading,
)
from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration, NoDayNight, NoWeather
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.value_object import ObjectId, PersonId, SpotId, WorldTick


class WorldFacts(Protocol):
    def now(self) -> WorldTick: ...

    def rules(self) -> WorldRules: ...

    def day_night(self) -> DayNightDeclaration | NoDayNight: ...

    def nouns(self) -> DeclaredNouns: ...

    def random(self) -> RandomSource: ...

    def people(self) -> tuple[PersonId, ...]: ...

    def whereabouts(self) -> WhereaboutsReading: ...

    def passages(self) -> PassageStatesReading: ...

    def atmospheres(self) -> SpotAtmospheresReading: ...

    def outcomes(self) -> PersonOutcomesReading: ...

    def membership(self) -> GroupMembershipReading: ...

    def clock(self) -> WorldClockReading: ...

    def weather(self) -> WeatherReading | NoWeather: ...

    def world_stage(self) -> WorldStageReading | NoWorldStages: ...

    def vitals(self, person: PersonId) -> PersonVitalsReading: ...

    def inventory(self, person: PersonId) -> PersonInventoryReading: ...

    def item(self, item: ItemInstanceId) -> ItemReading: ...

    def object_state(self, obj: ObjectId) -> ObjectStateReading: ...

    def ground_items(self, spot: SpotId) -> GroundItemsReading: ...

    def search_progress(self, spot: SpotId) -> SpotSearchProgressReading: ...

    def group_decision(self, decision: GroupDecisionDeclaration) -> GroupDecisionReading: ...
