from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from ai_rpg_world.game_world.domain.condition.chance_occasion import ChanceOccasion
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.character.group_declaration import GroupDeclaration
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemSpecDeclaration,
    ObjectStateKeyDeclaration,
    StateValue,
)
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration, WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration, SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    NoDayNight,
    NoWeather,
    TimeOfDay,
    WeatherState,
)
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.objects_and_items import (
    GroundItems,
    Item,
    ObjectState,
    PersonInventory,
    SpotSearchProgress,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import (
    GroupMembership,
    LifeState,
    Outcome,
    PersonOutcomes,
    PersonVitals,
    Undecided,
)
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    FatigueAmount,
    Gold,
    GroupDecisionId,
    HungerAmount,
    ObjectId,
    PersonId,
    SpotId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import (
    AtSpot,
    Occupant,
    PassageStates,
    SpotAtmospheres,
    TravelInProgress,
    Whereabouts,
)
from ai_rpg_world.game_world.domain.world_progress import GroupDecision, Weather, WorldClock, WorldStage


class WorldInMemory:
    def __init__(
        self,
        *,
        world: WorldId,
        people: tuple[PersonId, ...] = (),
        spots: tuple[SpotDeclaration, ...] = (),
        passages: tuple[PassageDeclaration, ...] = (),
        vitals: tuple[PersonVitals, ...] = (),
        inventories: tuple[PersonInventory, ...] = (),
        items: tuple[Item, ...] = (),
        object_states: tuple[ObjectState, ...] = (),
        world_stage: WorldStage | NoWorldStages = NoWorldStages(),
        stage_declarations: tuple[WorldStageDeclaration, ...] = (),
        day_night: DayNightDeclaration | NoDayNight = NoDayNight(),
        weather: Weather | NoWeather = NoWeather(),
        rolls: Mapping[ChanceOccasion, float] = MappingProxyType({}),
    ) -> None:
        self.people = people
        self.clock_aggregate = WorldClock(world)
        self.whereabouts = Whereabouts(world)
        self.passages = PassageStates(world, passages)
        self.atmospheres = SpotAtmospheres(world, spots)
        self.outcomes = PersonOutcomes.start(world, people)
        self.membership = GroupMembership(world)
        self.vitals = {v.person: v for v in vitals}
        self.inventories = {i.person_id: i for i in inventories}
        self.items = {i.item_id: i for i in items}
        self.object_states = {o.object_id: o for o in object_states}
        self.ground_items: dict[SpotId, GroundItems] = {}
        self.search_progresses: dict[SpotId, SpotSearchProgress] = {}
        self.group_decisions: dict[GroupDecisionId, GroupDecision] = {}
        self.world_stage = world_stage
        self.stage_declarations = {s.stage_id: s for s in stage_declarations}
        self.day_night = day_night
        self.weather = weather
        self.rolls = dict(rolls)

    def facts(self) -> WorldFacts:
        return _FactsInMemory(self)

    def aggregates(self) -> WorldAggregates:
        return _AggregatesInMemory(self)

    def clock(self) -> WorldClock:
        return self.clock_aggregate

    def search_progress(self, spot: SpotId) -> SpotSearchProgress:
        return self.search_progresses.setdefault(spot, SpotSearchProgress(spot))


class _FactsInMemory(WorldFacts):
    def __init__(self, world: WorldInMemory) -> None:
        self._world = world

    def now(self) -> WorldTick:
        return self._world.clock_aggregate.now()

    def world_stage(self) -> WorldStageDeclaration | NoWorldStages:
        stage = self._world.world_stage
        if isinstance(stage, NoWorldStages):
            return stage
        return self._world.stage_declarations[stage.current()]

    def ticks_in_world_stage(self) -> Ticks:
        stage = self._world.world_stage
        if isinstance(stage, NoWorldStages):
            raise LookupError("this world declares no world stages")
        return self.now().ticks_since(stage.entered_at())

    def time_of_day(self) -> TimeOfDay | NoDayNight:
        day_night = self._world.day_night
        if isinstance(day_night, NoDayNight):
            return day_night
        return self._world.clock_aggregate.time_of_day(day_night)

    def weather(self) -> WeatherState | NoWeather:
        weather = self._world.weather
        if isinstance(weather, NoWeather):
            return weather
        return weather.current()

    def object_value(self, key: ObjectStateKeyDeclaration) -> StateValue:
        return self._world.object_states[key.object_id].value_of(key, self.now())

    def item_count(self, person: PersonId, item_spec: ItemSpecDeclaration) -> Count:
        carried = self._world.inventories[person].items()
        return Count(sum(1 for item in carried if self._is_of(item, item_spec)))

    def is_holding(self, person: PersonId, item_spec: ItemSpecDeclaration) -> bool:
        return any(self._is_of(item, item_spec) for item in self._world.inventories[person].held_items())

    def spot_of(self, occupant: Occupant) -> SpotId | TravelInProgress:
        location = self._world.whereabouts.location_of(occupant)
        if isinstance(location, AtSpot):
            return location.spot
        return location

    def is_member(self, person: PersonId, group: GroupDeclaration) -> bool:
        return self._world.membership.is_member(person, group)

    def gold_of(self, person: PersonId) -> Gold:
        return self._world.inventories[person].available_gold()

    def hunger_of(self, person: PersonId) -> HungerAmount:
        return self._world.vitals[person].hunger()

    def fatigue_of(self, person: PersonId) -> FatigueAmount:
        return self._world.vitals[person].fatigue()

    def life_state(self, person: PersonId) -> LifeState:
        return self._world.vitals[person].life_state()

    def outcome_of(self, person: PersonId) -> Outcome | Undecided:
        return self._world.outcomes.outcome_of(person)

    def all_outcomes_decided(self) -> bool:
        return self._world.outcomes.all_decided()

    def search_count(self, person: PersonId, spot: SpotId) -> Count:
        return self._world.search_progress(spot).search_count(person)

    def people(self) -> tuple[PersonId, ...]:
        return self._world.people

    def roll(self, occasion: ChanceOccasion) -> float:
        if occasion not in self._world.rolls:
            raise LookupError(f"no roll was given for {occasion!r}")
        return self._world.rolls[occasion]

    def _is_of(self, item: ItemInstanceId, item_spec: ItemSpecDeclaration) -> bool:
        return self._world.items[item].spec_id == item_spec.item_spec_id


class _AggregatesInMemory(WorldAggregates):
    def __init__(self, world: WorldInMemory) -> None:
        self._world = world

    def passages(self) -> PassageStates:
        return self._world.passages

    def atmospheres(self) -> SpotAtmospheres:
        return self._world.atmospheres

    def whereabouts(self) -> Whereabouts:
        return self._world.whereabouts

    def vitals(self, person: PersonId) -> PersonVitals:
        return self._world.vitals[person]

    def outcomes(self) -> PersonOutcomes:
        return self._world.outcomes

    def membership(self) -> GroupMembership:
        return self._world.membership

    def inventory(self, person: PersonId) -> PersonInventory:
        return self._world.inventories[person]

    def item(self, item: ItemInstanceId) -> Item:
        return self._world.items[item]

    def object_state(self, obj: ObjectId) -> ObjectState:
        return self._world.object_states[obj]

    def ground_items(self, spot: SpotId) -> GroundItems:
        return self._world.ground_items.setdefault(spot, GroundItems(spot))

    def world_stage(self) -> WorldStage:
        stage = self._world.world_stage
        if isinstance(stage, NoWorldStages):
            raise LookupError("this world declares no world stages")
        return stage

    def group_decision(self, decision: GroupDecisionDeclaration) -> GroupDecision:
        return self._world.group_decisions.setdefault(decision.decision_id, GroupDecision(decision))

    def weather(self) -> Weather:
        weather = self._world.weather
        if isinstance(weather, NoWeather):
            raise LookupError("this world declares no weather")
        return weather
