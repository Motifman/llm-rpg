from __future__ import annotations

import uuid
from collections.abc import Callable, Hashable
from typing import TypeVar

from ai_rpg_world.game_world.domain.condition.aggregate_readings import (
    GroundItemsReading,
    GroupDecisionReading,
    GroupMembershipReading,
    ItemReading,
    LatestActionsReading,
    MissedNoticesReading,
    ObjectStateReading,
    PassageStatesReading,
    PeopleRegisterReading,
    PersonInventoryReading,
    PersonOutcomesReading,
    PersonVitalsReading,
    ScenarioProgressReading,
    SpotAtmospheresReading,
    SpotSearchProgressReading,
    WeatherReading,
    WhereaboutsReading,
    WorldClockReading,
    WorldFlagsReading,
    WorldStageReading,
)
from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration, NoDayNight, NoWeather
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.exception.world_contents_exception import AggregateNotInWorldException
from ai_rpg_world.game_world.domain.objects_and_items import (
    GroundItems,
    Item,
    ObjectState,
    PersonInventory,
    SpotSearchProgress,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import PeopleRegister
from ai_rpg_world.game_world.domain.person import GroupMembership, PersonOutcomes, PersonVitals
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.value_object import GroupDecisionId, ObjectId, PersonId, SpotId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import PassageStates, SpotAtmospheres, Whereabouts
from ai_rpg_world.game_world.domain.world_progress import GroupDecision, Weather, WorldClock, WorldStage
from ai_rpg_world.game_world.domain.world_records import LatestActions, MissedNotices, ScenarioProgress, WorldFlags

_Key = TypeVar("_Key", bound=Hashable)
_Aggregate = TypeVar("_Aggregate")


class InMemoryWorld:
    def __init__(
        self,
        *,
        rules: WorldRules,
        nouns: DeclaredNouns,
        day_night: DayNightDeclaration | NoDayNight,
        random: RandomSource,
        people: tuple[PersonId, ...],
        people_register: PeopleRegister,
        whereabouts: Whereabouts,
        passages: PassageStates,
        atmospheres: SpotAtmospheres,
        outcomes: PersonOutcomes,
        membership: GroupMembership,
        clock: WorldClock,
        weather: Weather | NoWeather,
        world_stage: WorldStage | NoWorldStages,
        flags: WorldFlags,
        scenario_progress: ScenarioProgress,
        latest_actions: LatestActions,
        vitals: tuple[PersonVitals, ...],
        inventories: tuple[PersonInventory, ...],
        items: tuple[Item, ...],
        object_states: tuple[ObjectState, ...],
        ground_items: tuple[GroundItems, ...],
        search_progresses: tuple[SpotSearchProgress, ...],
        missed_notices: tuple[MissedNotices, ...],
        group_decisions: tuple[GroupDecision, ...],
    ) -> None:
        self._rules = rules
        self._nouns = nouns
        self._day_night = day_night
        self._random = random
        self._people = people
        self._people_register = people_register
        self._whereabouts = whereabouts
        self._passages = passages
        self._atmospheres = atmospheres
        self._outcomes = outcomes
        self._membership = membership
        self._clock = clock
        self._weather = weather
        self._world_stage = world_stage
        self._flags = flags
        self._scenario_progress = scenario_progress
        self._latest_actions = latest_actions
        self._vitals = _by_owner(vitals, lambda v: v.person, "vitals")
        self._inventories = _by_owner(inventories, lambda i: i.person_id, "inventory")
        self._items = _by_owner(items, lambda i: i.item_id, "item")
        self._object_states = _by_owner(object_states, lambda o: o.object_id, "object state")
        self._ground_items = _by_owner(ground_items, lambda g: g.spot_id, "ground items")
        self._search_progresses = _by_owner(search_progresses, lambda s: s.spot_id, "search progress")
        self._missed_notices = _by_owner(missed_notices, lambda m: m.person, "missed notices")
        self._group_decisions: dict[GroupDecisionId, GroupDecision] = _by_owner(
            group_decisions, lambda d: d.decision_id, "group decision"
        )

    def facts(self) -> WorldFacts:
        return _InMemoryWorldFacts(self)

    def aggregates(self) -> WorldAggregates:
        return _InMemoryWorldAggregates(self)

    def clock(self) -> WorldClock:
        return self._clock

    def scenario_progress(self) -> ScenarioProgress:
        return self._scenario_progress

    def latest_actions(self) -> LatestActions:
        return self._latest_actions

    def people_register(self) -> PeopleRegister:
        return self._people_register


def _by_owner(
    aggregates: tuple[_Aggregate, ...], owner: Callable[[_Aggregate], _Key], kind: str
) -> dict[_Key, _Aggregate]:
    keyed: dict[_Key, _Aggregate] = {}
    for aggregate in aggregates:
        key = owner(aggregate)
        if key in keyed:
            raise ValueError(f"two {kind} aggregates belong to {key}")
        keyed[key] = aggregate
    return keyed


def _find(keyed: dict[_Key, _Aggregate], key: _Key, kind: str) -> _Aggregate:
    try:
        return keyed[key]
    except KeyError:
        raise AggregateNotInWorldException(f"no {kind} of {key} is in this world") from None


class _InMemoryWorldAggregates(WorldAggregates):
    def __init__(self, world: InMemoryWorld) -> None:
        self._world = world

    def flags(self) -> WorldFlags:
        return self._world._flags

    def passages(self) -> PassageStates:
        return self._world._passages

    def atmospheres(self) -> SpotAtmospheres:
        return self._world._atmospheres

    def whereabouts(self) -> Whereabouts:
        return self._world._whereabouts

    def vitals(self, person: PersonId) -> PersonVitals:
        return _find(self._world._vitals, person, "vitals")

    def outcomes(self) -> PersonOutcomes:
        return self._world._outcomes

    def membership(self) -> GroupMembership:
        return self._world._membership

    def inventory(self, person: PersonId) -> PersonInventory:
        return _find(self._world._inventories, person, "inventory")

    def item(self, item: ItemInstanceId) -> Item:
        return _find(self._world._items, item, "item")

    def object_state(self, obj: ObjectId) -> ObjectState:
        return _find(self._world._object_states, obj, "object state")

    def ground_items(self, spot: SpotId) -> GroundItems:
        return _find(self._world._ground_items, spot, "ground items")

    def search_progress(self, spot: SpotId) -> SpotSearchProgress:
        return _find(self._world._search_progresses, spot, "search progress")

    def missed_notices(self, person: PersonId) -> MissedNotices:
        return _find(self._world._missed_notices, person, "missed notices")

    def world_stage(self) -> WorldStage:
        stage = self._world._world_stage
        if isinstance(stage, NoWorldStages):
            raise AggregateNotInWorldException("this world declares no world stages")
        return stage

    def group_decision(self, decision: GroupDecisionDeclaration) -> GroupDecision:
        return _find(self._world._group_decisions, decision.decision_id, "group decision")

    def weather(self) -> Weather:
        weather = self._world._weather
        if isinstance(weather, NoWeather):
            raise AggregateNotInWorldException("this world declares no weather")
        return weather

    def bring_item_into_world(self, spec: ItemSpecDeclaration, now: WorldTick) -> ItemInstanceId:
        item = Item.come_into_world(ItemInstanceId(str(uuid.uuid4())), spec, now)
        self._world._items[item.item_id] = item
        return item.item_id

    def take_item_out_of_world(self, item: ItemInstanceId) -> None:
        self.item(item).leave_world()
        del self._world._items[item]


class _InMemoryWorldFacts(WorldFacts):
    def __init__(self, world: InMemoryWorld) -> None:
        self._world = world
        self._aggregates = _InMemoryWorldAggregates(world)

    def now(self) -> WorldTick:
        return self._world._clock.now()

    def rules(self) -> WorldRules:
        return self._world._rules

    def day_night(self) -> DayNightDeclaration | NoDayNight:
        return self._world._day_night

    def nouns(self) -> DeclaredNouns:
        return self._world._nouns

    def random(self) -> RandomSource:
        return self._world._random

    def people(self) -> tuple[PersonId, ...]:
        return self._world._people

    def people_register(self) -> PeopleRegisterReading:
        return self._world._people_register

    def whereabouts(self) -> WhereaboutsReading:
        return self._world._whereabouts

    def passages(self) -> PassageStatesReading:
        return self._world._passages

    def atmospheres(self) -> SpotAtmospheresReading:
        return self._world._atmospheres

    def outcomes(self) -> PersonOutcomesReading:
        return self._world._outcomes

    def membership(self) -> GroupMembershipReading:
        return self._world._membership

    def clock(self) -> WorldClockReading:
        return self._world._clock

    def weather(self) -> WeatherReading | NoWeather:
        return self._world._weather

    def world_stage(self) -> WorldStageReading | NoWorldStages:
        return self._world._world_stage

    def flags(self) -> WorldFlagsReading:
        return self._world._flags

    def scenario_progress(self) -> ScenarioProgressReading:
        return self._world._scenario_progress

    def latest_actions(self) -> LatestActionsReading:
        return self._world._latest_actions

    def vitals(self, person: PersonId) -> PersonVitalsReading:
        return self._aggregates.vitals(person)

    def inventory(self, person: PersonId) -> PersonInventoryReading:
        return self._aggregates.inventory(person)

    def item(self, item: ItemInstanceId) -> ItemReading:
        return self._aggregates.item(item)

    def object_state(self, obj: ObjectId) -> ObjectStateReading:
        return self._aggregates.object_state(obj)

    def ground_items(self, spot: SpotId) -> GroundItemsReading:
        return self._aggregates.ground_items(spot)

    def search_progress(self, spot: SpotId) -> SpotSearchProgressReading:
        return self._aggregates.search_progress(spot)

    def missed_notices(self, person: PersonId) -> MissedNoticesReading:
        return self._aggregates.missed_notices(person)

    def group_decision(self, decision: GroupDecisionDeclaration) -> GroupDecisionReading:
        return self._aggregates.group_decision(decision)
