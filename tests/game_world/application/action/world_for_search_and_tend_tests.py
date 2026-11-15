from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.action.search_spot import SearchSpot, SearchSpotCommand
from ai_rpg_world.game_world.application.action.tend_fallen_person import (
    TendFallenPerson,
    TendFallenPersonCommand,
)
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.built_in_attempts import SpotSearchAttempt, TendAttempt
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.person_conditions import SearchCountAtLeastCondition
from ai_rpg_world.game_world.domain.condition.subject import Actor
from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.discoverable_declaration import (
    DiscoverableDeclaration,
    Finding,
)
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.effect.item_effects import GiveItemEffect
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.rules.tend_rule import NoTending, TendRule
from ai_rpg_world.game_world.domain.value_object import Count, Damage, PersonId, Rate, SpotId, WorldId
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds
from tests.game_world.support.world_design_for_tests import (
    built_in_action_perceptions,
    character,
    compose_world,
    item_spec,
    nouns,
    passage,
    spot,
)
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

WORLD = WorldId("search_and_tend_world")
ALICE = PersonId("alice")
BOB = PersonId("bob")
CAVE = SpotId("cave")
KEY = item_spec("key")
PEBBLE = item_spec("pebble")
OLD_KEY = DiscoverableDeclaration(
    discoverable_id=DiscoverableId("old_key"),
    spot_id=CAVE,
    found_text=TextWithUnassignedPeople("岩の隙間に古い鍵があった。"),
    condition=SearchCountAtLeastCondition(Actor(), Count(2), NoText()),
    when_found=GiveItemEffect(Actor(), KEY, Count(1)),
    finding=Finding.ONCE_IN_WORLD,
)
SHINY_PEBBLE = DiscoverableDeclaration(
    discoverable_id=DiscoverableId("shiny_pebble"),
    spot_id=CAVE,
    found_text=TextWithUnassignedPeople("光る小石を拾った。"),
    condition=AlwaysHolds(),
    when_found=GiveItemEffect(Actor(), PEBBLE, Count(1)),
    finding=Finding.ONCE_PER_PERSON,
)


class WorldForSearchAndTend:
    def __init__(self, *, tending: TendRule | NoTending = TendRule(revive_hp_rate=Rate(0.5))) -> None:
        self.design = _design(tending)
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=WORLD,
            scenario="search_and_tend_world",
            scenario_hash="search_and_tend_world",
            design=self.design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=WORLD, design=self.design))
        distributor = CommittedEventsDistributor()
        self.events_received: list[DomainEvent] = []
        distributor.register_receiver(self)
        self.scope = CommandScope(self.store, distributor)
        self.carry_out = CarryOutAction(self.scope, self.design)

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.events_received.extend(events)

    def search(self, actor: PersonId) -> ActionReply:
        return SearchSpot(self.carry_out, self.design)(SearchSpotCommand(SpotSearchAttempt(actor)))

    def tend(self, actor: PersonId, target: PersonId) -> ActionReply:
        return TendFallenPerson(self.carry_out)(TendFallenPersonCommand(TendAttempt(actor, target)))

    def knock_down(self, person: PersonId) -> None:
        self.scope.run(
            lambda session: (
                session.aggregates().vitals(person).take_damage(Damage(1000), session.facts().now(), WorldHappening())
            )
        )

    def pass_ticks(self, count: int) -> None:
        for _ in range(count):
            self.scope.run(lambda session: session.clock().advance(self.design.day_night))

    def count_of(self, person: PersonId, spec: ItemSpecDeclaration) -> Count:
        session = self.store.session()
        count = session.facts().inventory(person).count_of(spec.item_spec_id)
        session.roll_back()
        return count

    def read(self) -> WorldSession:
        return self.store.session()


def _design(tending: TendRule | NoTending) -> WorldDesign:
    return compose_world(
        nouns(
            spots=[spot("cave"), spot("shore")],
            passages=[passage("tunnel", ("cave", "shore"))],
            item_specs=[KEY, PEBBLE],
            characters=[character("alice", "cave"), character("bob", "cave")],
        ),
        discoverables=[OLD_KEY, SHINY_PEBBLE],
        world_rules=replace(world_rules_for_tests(), tend=tending),
        built_in_action_perceptions_=built_in_action_perceptions(),
    )
