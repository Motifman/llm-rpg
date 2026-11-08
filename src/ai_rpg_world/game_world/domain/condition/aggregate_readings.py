from __future__ import annotations

from typing import Protocol

from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.declaration.character import GroupDeclaration, GroupingDeclaration
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemStateKeyDeclaration,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
    StateValue,
)
from ai_rpg_world.game_world.domain.declaration.spot import (
    PassageDeclaration,
    SpotAtmosphere,
    SpotDeclaration,
    SpotSectionDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    TimeOfDay,
    WeatherState,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import LifeState, NotInAnyGroup, Outcome, Undecided
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueRule
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    FatigueAmount,
    Gold,
    GroupId,
    HitPoints,
    HungerAmount,
    ItemSpecId,
    PassageId,
    PersonId,
    Ticks,
    WorldStageId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import Location, Occupant, PassageInState


class WhereaboutsReading(Protocol):
    def location_of(self, occupant: Occupant) -> Location: ...

    def occupants_at(self, spot: SpotDeclaration) -> tuple[Occupant, ...]: ...

    def are_together(self, actor: Occupant, target: Occupant) -> bool: ...

    def is_at(self, occupant: Occupant, spot: SpotDeclaration) -> bool: ...

    def is_in_section(self, occupant: Occupant, section: SpotSectionDeclaration) -> bool: ...

    def can_reach(
        self, occupant: Occupant, obj: ObjectDeclaration, sections: tuple[SpotSectionDeclaration, ...]
    ) -> bool: ...


class PassageStatesReading(Protocol):
    def is_traversable(self, passage: PassageDeclaration) -> bool: ...

    def closed_passages(self) -> frozenset[PassageId]: ...

    def passages_from(
        self, spot: SpotDeclaration, declared: tuple[PassageDeclaration, ...]
    ) -> tuple[PassageId, ...]: ...

    def in_state(self, passage: PassageDeclaration) -> PassageInState: ...


class SpotAtmospheresReading(Protocol):
    def atmosphere_of(self, spot: SpotDeclaration) -> SpotAtmosphere: ...


class PersonOutcomesReading(Protocol):
    def outcome_of(self, person: PersonId) -> Outcome | Undecided: ...

    def all_decided(self) -> bool: ...

    def undecided_people(self) -> tuple[PersonId, ...]: ...


class GroupMembershipReading(Protocol):
    def is_member(self, person: PersonId, group: GroupDeclaration) -> bool: ...

    def members_of(self, group: GroupDeclaration) -> frozenset[PersonId]: ...

    def group_of(self, person: PersonId, grouping: GroupingDeclaration) -> GroupId | NotInAnyGroup: ...


class WorldClockReading(Protocol):
    def now(self) -> WorldTick: ...

    def time_of_day(self, day_night: DayNightDeclaration) -> TimeOfDay: ...


class WeatherReading(Protocol):
    def current(self) -> WeatherState: ...


class WorldStageReading(Protocol):
    def current(self) -> WorldStageId: ...

    def entered_at(self) -> WorldTick: ...


class PersonVitalsReading(Protocol):
    def is_busy(self, now: WorldTick) -> bool: ...

    def hp(self) -> HitPoints: ...

    def hunger(self) -> HungerAmount: ...

    def fatigue(self) -> FatigueAmount: ...

    def can_act(self) -> bool: ...

    def is_dead(self) -> bool: ...

    def life_state(self) -> LifeState: ...

    def occupant_in_world(self, departed_persons_act: bool) -> Occupant: ...

    def fatigue_reached_limit(self, rule: FatigueRule) -> bool: ...


class PersonInventoryReading(Protocol):
    def items(self) -> tuple[ItemInstanceId, ...]: ...

    def held_items(self) -> tuple[ItemInstanceId, ...]: ...

    def packed_items(self) -> tuple[ItemInstanceId, ...]: ...

    def is_full(self) -> bool: ...

    def available_gold(self) -> Gold: ...

    def count_of(self, spec: ItemSpecId) -> Count: ...

    def items_to_give_up(self, spec: ItemSpecId, count: Count) -> tuple[ItemInstanceId, ...]: ...

    def random_packed_item(self, random: RandomSource) -> ItemInstanceId: ...


class ItemReading(Protocol):
    @property
    def spec_id(self) -> ItemSpecId: ...

    def value_of(self, key: ItemStateKeyDeclaration) -> StateValue: ...

    def age(self, now: WorldTick) -> Ticks: ...

    def gives_light(self) -> bool: ...


class ObjectStateReading(Protocol):
    def value_of(self, key: ObjectStateKeyDeclaration, now: WorldTick) -> StateValue: ...

    def is_revealed(self) -> bool: ...


class GroundItemsReading(Protocol):
    def items(self) -> tuple[ItemInstanceId, ...]: ...

    def contains(self, item: ItemInstanceId) -> bool: ...


class SpotSearchProgressReading(Protocol):
    def search_count(self, person: PersonId) -> Count: ...


class GroupDecisionReading(Protocol):
    def is_open(self) -> bool: ...
