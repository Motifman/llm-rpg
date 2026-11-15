from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.value_object import Capacity, Damage, HandsNeeded, ItemSpecId, PersonId, WorldId
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.world_design_for_tests import character, compose_world, item_spec, nouns, passage, spot

WORLD = WorldId("item_action_world")
ALICE = PersonId("alice")
BOB = PersonId("bob")
CAROL = PersonId("carol")
CAMP = spot("camp")
RIVER = spot("river")
PICKAXE = replace(item_spec("pickaxe"), hands_needed=HandsNeeded(2))
ROPE = item_spec("rope")


class WorldForItemActions:
    def __init__(self, *, alice_carries: tuple[ItemSpecId, ...] = (), bob_capacity: int = 2) -> None:
        self.design = _design(alice_carries, bob_capacity)
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=WORLD,
            scenario="item_action_world",
            scenario_hash="item_action_world",
            design=self.design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=WORLD, design=self.design))
        self.scope = CommandScope(self.store, CommittedEventsDistributor())
        self.carry_out = CarryOutAction(self.scope, self.design)

    def lay_on_ground_at_camp(self) -> ItemInstanceId:
        def lay(session: WorldSession) -> ItemInstanceId:
            world = session.aggregates()
            item = world.bring_item_into_world(PICKAXE, session.facts().now())
            world.ground_items(CAMP.spot_id).place(item)
            return item

        return self.scope.run(lay)

    def pass_ticks(self, count: int) -> None:
        for _ in range(count):
            self.scope.run(lambda session: session.clock().advance(self.design.day_night))

    def fell(self, person: PersonId) -> None:
        self.scope.run(
            lambda session: (
                session.aggregates().vitals(person).take_damage(Damage(999), session.facts().now(), WorldHappening())
            )
        )

    def carried_by(self, person: PersonId) -> tuple[ItemInstanceId, ...]:
        return self._read(lambda facts: facts.inventory(person).items())

    def held_by(self, person: PersonId) -> tuple[ItemInstanceId, ...]:
        return self._read(lambda facts: facts.inventory(person).held_items())

    def on_ground_at_camp(self) -> tuple[ItemInstanceId, ...]:
        return self._read(lambda facts: facts.ground_items(CAMP.spot_id).items())

    def _read(self, reading: Callable[[WorldFacts], tuple[ItemInstanceId, ...]]) -> tuple[ItemInstanceId, ...]:
        session = self.store.session()
        try:
            return reading(session.facts())
        finally:
            session.roll_back()


def _design(alice_carries: tuple[ItemSpecId, ...], bob_capacity: int) -> WorldDesign:
    return compose_world(
        nouns(
            spots=[CAMP, RIVER],
            passages=[passage("path", ("camp", "river"))],
            item_specs=[PICKAXE, ROPE],
            characters=[
                replace(character("alice", "camp"), initial_items=alice_carries, pack_capacity=Capacity(2)),
                replace(character("bob", "camp"), pack_capacity=Capacity(bob_capacity)),
                character("carol", "river"),
            ],
        ),
    )
