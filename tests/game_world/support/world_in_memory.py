from __future__ import annotations

import uuid

from ai_rpg_world.game_world.domain.condition.aggregate_readings import (
    GroundItemsReading,
    GroupDecisionReading,
    GroupMembershipReading,
    ItemReading,
    LatestActionsReading,
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
from ai_rpg_world.game_world.domain.declaration.character import CharacterDeclaration
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration, ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration, WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration, SpotDeclaration, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration, NoDayNight, NoWeather
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
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
from ai_rpg_world.game_world.domain.value_object import GroupDecisionId, ObjectId, PersonId, SpotId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import PassageStates, SpotAtmospheres, Whereabouts
from ai_rpg_world.game_world.domain.world_progress import GroupDecision, Weather, WorldClock, WorldStage
from ai_rpg_world.game_world.domain.world_records import LatestActions, ScenarioProgress, WorldFlags
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests


class FractionsInOrder(RandomSource):
    def __init__(self, fractions: tuple[float, ...]) -> None:
        for fraction in fractions:
            if not 0.0 <= fraction < 1.0:
                raise ValueError(f"a fraction must be in [0, 1), got {fraction}")
        self._left = list(fractions)

    def next_fraction(self) -> float:
        if not self._left:
            raise LookupError("every fraction the test gave has been drawn")
        return self._left.pop(0)


class WorldInMemory:
    def __init__(
        self,
        *,
        world: WorldId,
        rules: WorldRules | None = None,
        people: tuple[PersonId, ...] = (),
        characters: tuple[CharacterDeclaration, ...] = (),
        spots: tuple[SpotDeclaration, ...] = (),
        passages: tuple[PassageDeclaration, ...] = (),
        objects: tuple[ObjectDeclaration, ...] = (),
        sections: tuple[SpotSectionDeclaration, ...] = (),
        vitals: tuple[PersonVitals, ...] = (),
        inventories: tuple[PersonInventory, ...] = (),
        items: tuple[Item, ...] = (),
        object_states: tuple[ObjectState, ...] = (),
        world_stage: WorldStage | NoWorldStages = NoWorldStages(),
        stage_declarations: tuple[WorldStageDeclaration, ...] = (),
        day_night: DayNightDeclaration | NoDayNight = NoDayNight(),
        weather: Weather | NoWeather = NoWeather(),
        fractions: tuple[float, ...] = (),
    ) -> None:
        self.rules = rules if rules is not None else world_rules_for_tests()
        self.people = people
        self.nouns = DeclaredNouns(
            flags=(),
            spots=spots,
            passages=passages,
            objects=objects,
            item_specs=(),
            groupings=(),
            groups=(),
            characters=characters,
            world_stages=stage_declarations,
            group_decisions=(),
            sections=sections,
            outcomes=(),
        )
        self.clock_aggregate = WorldClock(world)
        self.whereabouts = Whereabouts(world)
        self.passages = PassageStates(world, passages)
        self.atmospheres = SpotAtmospheres(world, spots)
        self.outcomes = PersonOutcomes.start(world, people)
        self.membership = GroupMembership(world)
        self.people_register = PeopleRegister.from_characters(world, characters)
        self.vitals = {v.person: v for v in vitals}
        self.inventories = {i.person_id: i for i in inventories}
        self.items = {i.item_id: i for i in items}
        self.object_states = {o.object_id: o for o in object_states}
        self.ground_items: dict[SpotId, GroundItems] = {}
        self.search_progresses: dict[SpotId, SpotSearchProgress] = {}
        self.group_decisions: dict[GroupDecisionId, GroupDecision] = {}
        self.world_stage = world_stage
        self.flags = WorldFlags(world)
        self.scenario_progress = ScenarioProgress(world)
        self.latest_actions = LatestActions(world)
        self.day_night = day_night
        self.weather = weather
        self.random = FractionsInOrder(fractions)

    def facts(self) -> WorldFacts:
        return _FactsInMemory(self)

    def aggregates(self) -> WorldAggregates:
        return _AggregatesInMemory(self)

    def clock(self) -> WorldClock:
        return self.clock_aggregate

    def ground_items_at(self, spot: SpotId) -> GroundItems:
        return self.ground_items.setdefault(spot, GroundItems(spot))

    def search_progress_at(self, spot: SpotId) -> SpotSearchProgress:
        return self.search_progresses.setdefault(spot, SpotSearchProgress(spot))

    def group_decision_of(self, decision: GroupDecisionDeclaration) -> GroupDecision:
        return self.group_decisions.setdefault(decision.decision_id, GroupDecision(decision))


class _FactsInMemory(WorldFacts):
    def __init__(self, world: WorldInMemory) -> None:
        self._world = world

    def now(self) -> WorldTick:
        return self._world.clock_aggregate.now()

    def rules(self) -> WorldRules:
        return self._world.rules

    def day_night(self) -> DayNightDeclaration | NoDayNight:
        return self._world.day_night

    def nouns(self) -> DeclaredNouns:
        return self._world.nouns

    def random(self) -> RandomSource:
        return self._world.random

    def people(self) -> tuple[PersonId, ...]:
        return self._world.people

    def people_register(self) -> PeopleRegisterReading:
        return self._world.people_register

    def whereabouts(self) -> WhereaboutsReading:
        return self._world.whereabouts

    def passages(self) -> PassageStatesReading:
        return self._world.passages

    def atmospheres(self) -> SpotAtmospheresReading:
        return self._world.atmospheres

    def outcomes(self) -> PersonOutcomesReading:
        return self._world.outcomes

    def membership(self) -> GroupMembershipReading:
        return self._world.membership

    def clock(self) -> WorldClockReading:
        return self._world.clock_aggregate

    def weather(self) -> WeatherReading | NoWeather:
        return self._world.weather

    def world_stage(self) -> WorldStageReading | NoWorldStages:
        return self._world.world_stage

    def flags(self) -> WorldFlagsReading:
        return self._world.flags

    def scenario_progress(self) -> ScenarioProgressReading:
        return self._world.scenario_progress

    def latest_actions(self) -> LatestActionsReading:
        return self._world.latest_actions

    def vitals(self, person: PersonId) -> PersonVitalsReading:
        return self._world.vitals[person]

    def inventory(self, person: PersonId) -> PersonInventoryReading:
        return self._world.inventories[person]

    def item(self, item: ItemInstanceId) -> ItemReading:
        return self._world.items[item]

    def object_state(self, obj: ObjectId) -> ObjectStateReading:
        return self._world.object_states[obj]

    def ground_items(self, spot: SpotId) -> GroundItemsReading:
        return self._world.ground_items_at(spot)

    def search_progress(self, spot: SpotId) -> SpotSearchProgressReading:
        return self._world.search_progress_at(spot)

    def group_decision(self, decision: GroupDecisionDeclaration) -> GroupDecisionReading:
        return self._world.group_decision_of(decision)


class _AggregatesInMemory(WorldAggregates):
    def __init__(self, world: WorldInMemory) -> None:
        self._world = world

    def flags(self) -> WorldFlags:
        return self._world.flags

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
        return self._world.ground_items_at(spot)

    def search_progress(self, spot: SpotId) -> SpotSearchProgress:
        return self._world.search_progress_at(spot)

    def world_stage(self) -> WorldStage:
        stage = self._world.world_stage
        if isinstance(stage, NoWorldStages):
            raise LookupError("this world declares no world stages")
        return stage

    def group_decision(self, decision: GroupDecisionDeclaration) -> GroupDecision:
        return self._world.group_decision_of(decision)

    def weather(self) -> Weather:
        weather = self._world.weather
        if isinstance(weather, NoWeather):
            raise LookupError("this world declares no weather")
        return weather

    def bring_item_into_world(self, spec: ItemSpecDeclaration, now: WorldTick) -> ItemInstanceId:
        item = Item.come_into_world(ItemInstanceId(str(uuid.uuid4())), spec, now)
        self._world.items[item.item_id] = item
        return item.item_id

    def take_item_out_of_world(self, item: ItemInstanceId) -> None:
        self._world.items.pop(item).leave_world()
