from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TypeVar

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.world_store import AggregateWithMemento, WorldSession
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.person import PersonVitals, WorldHappening
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.value_object import Damage, HitPoints, PersonId, Ticks, WorldId, WorldTick
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

WORLD = WorldId("handler_world")
NOW = WorldTick(0)
FULL_HP = HitPoints(current=10, maximum=10)

_Answer = TypeVar("_Answer")


def rules(*, departed_persons_act: bool = False) -> WorldRules:
    return replace(world_rules_for_tests(), departed_persons_act=departed_persons_act)


class WiredWorld:
    def __init__(self, design: WorldDesign, *aggregates: AggregateWithMemento) -> None:
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=WORLD,
            scenario="handlers.yaml",
            scenario_hash="hash-of-the-scenario",
            design=design,
            random=SeedableRandomSource(1),
        )
        self.store.start_world(aggregates)
        self.distributor = CommittedEventsDistributor()
        self.scope = CommandScope(self.store, self.distributor)

    def read(self, question: Callable[[WorldSession], _Answer]) -> _Answer:
        session = self.store.session()
        try:
            return question(session)
        finally:
            session.roll_back()


def healthy(person: PersonId) -> PersonVitals:
    return PersonVitals.start(person, FULL_HP)


def falls(person: PersonId) -> Callable[[WorldSession], None]:
    def work(session: WorldSession) -> None:
        session.aggregates().vitals(person).take_damage(Damage(FULL_HP.current), NOW, WorldHappening())

    return work


def falls_and_dies(person: PersonId) -> Callable[[WorldSession], None]:
    def work(session: WorldSession) -> None:
        falls(person)(session)
        vitals = session.aggregates().vitals(person)
        vitals.pass_time(NOW, DeathRule(grace=Ticks(0)), session.facts().rules().hunger)

    return work
