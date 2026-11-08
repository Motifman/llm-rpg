from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.declaration.character import GroupDeclaration, GroupingDeclaration
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemStateKeyDeclaration,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
    StateValue,
)
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration, WorldStageDeclaration
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
from ai_rpg_world.game_world.domain.people.person_handle import PersonHandle
from ai_rpg_world.game_world.domain.person import LifeState, NotInAnyGroup, Outcome, Undecided
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueRule
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    DescriptionText,
    DisplayName,
    FatigueAmount,
    Gold,
    GroupId,
    HitPoints,
    HungerAmount,
    InteractionId,
    ItemSpecId,
    PassageId,
    PersonId,
    Ticks,
    WorldStageId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import Location, Occupant, PassageInState

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.subject import Anyone
    from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
    from ai_rpg_world.game_world.domain.declaration.verb.discoverable_declaration import DiscoverableDeclaration
    from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
    from ai_rpg_world.game_world.domain.declaration.verb.reaction_declaration import ReactionDeclaration
    from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
    from ai_rpg_world.game_world.domain.world_records import NeverDone, NeverFired


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

    def declaration_in(self, nouns: DeclaredNouns) -> WorldStageDeclaration: ...


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

    def is_found(self, discoverable: DiscoverableDeclaration, person: PersonId) -> bool: ...


class ScenarioProgressReading(Protocol):
    def may_fire(self, happening: HappeningDeclaration, now: WorldTick) -> bool: ...

    def reaction_changed(self, reaction: ReactionDeclaration, truth: bool) -> bool: ...

    def last_fired_at(self, happening: HappeningDeclaration) -> WorldTick | NeverFired: ...


class LatestActionsReading(Protocol):
    def last_done_at(self, who: PersonId | Anyone, action: ActionKind | InteractionId) -> WorldTick | NeverDone: ...


class WorldFlagsReading(Protocol):
    def is_raised(self, flag: FlagDeclaration) -> bool: ...


class GroupDecisionReading(Protocol):
    def is_open(self) -> bool: ...


class PeopleRegisterReading(Protocol):
    def handle_of(self, person: PersonId) -> PersonHandle: ...

    def name_of(self, person: PersonId) -> DisplayName: ...

    def appearance_of(self, person: PersonId) -> DescriptionText: ...
