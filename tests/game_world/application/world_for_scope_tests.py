from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.eventing import DomainEvent, EventHandler
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import AggregateWithMemento, WorldSession
from ai_rpg_world.game_world.domain.action.trigger import WorldTimePassing
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.value_object import DescriptionText, FlagId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.world_records import WorldFlagRaisedEvent
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.world_design_for_tests import compose_world, item_spec, nouns, spot

WORLD = WorldId("scope_world")
NOW = WorldTick(3)
BELL = FlagDeclaration(FlagId("bell_rang"), DescriptionText("鐘が鳴った"), initially_raised=False)
DOOR = FlagDeclaration(FlagId("door_opened"), DescriptionText("扉が開いた"), initially_raised=False)
GATE = FlagDeclaration(FlagId("gate_opened"), DescriptionText("門が開いた"), initially_raised=False)
ROPE = item_spec("rope")


def store_holding(*aggregates: AggregateWithMemento) -> SqliteWorldStore:
    store = SqliteWorldStore.create(
        ":memory:",
        world_id=WORLD,
        scenario="scope.yaml",
        scenario_hash="hash-of-the-scenario",
        design=compose_world(nouns(flags=[BELL, DOOR, GATE], spots=[spot("cave")], item_specs=[ROPE])),
        random=SeedableRandomSource(1),
    )
    store.start_world(aggregates)
    return store


def raise_flag(flag: FlagDeclaration) -> Callable[[WorldSession], None]:
    return lambda session: session.aggregates().flags().raise_flag(flag, WorldTimePassing(NOW))


def raise_flag_unless_ended(flag: FlagDeclaration) -> Callable[[WorldSession], None]:
    def work(session: WorldSession) -> None:
        if not session.ending().has_ended():
            raise_flag(flag)(session)

    return work


def end_world(session: WorldSession) -> None:
    session.ending().end(NOW)


def raised(store: SqliteWorldStore, flag: FlagDeclaration) -> bool:
    session = store.session()
    is_raised = session.facts().flags().is_raised(flag)
    session.roll_back()
    return is_raised


class BatchesReceived:
    def __init__(self) -> None:
        self.batches: list[tuple[DomainEvent, ...]] = []

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.batches.append(events)

    def raised_flags(self) -> list[list[FlagId]]:
        return [[_raised_flag(event) for event in batch] for batch in self.batches]


def _raised_flag(event: DomainEvent) -> FlagId:
    assert isinstance(event, WorldFlagRaisedEvent)
    return event.flag_id


class OnFlagRaised(EventHandler[WorldFlagRaisedEvent]):
    def __init__(self, scope: CommandScope, flag: FlagDeclaration, *works: Callable[[WorldSession], None]) -> None:
        self._scope = scope
        self._flag = flag
        self._works = works
        self.handled = 0

    def handle(self, event: WorldFlagRaisedEvent) -> None:
        if event.flag_id != self._flag.flag_id:
            return
        self.handled += 1
        self._scope.run(lambda session: [work(session) for work in self._works])
