from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol, final

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.people import PeopleRegister
from ai_rpg_world.game_world.domain.world_progress import WorldClock, WorldEnding
from ai_rpg_world.game_world.domain.world_records import LatestActions, ScenarioProgress


@final
@dataclass(frozen=True)
class AcceptedApart:
    pass


class WorldSession(Protocol):
    def facts(self) -> WorldFacts: ...

    def aggregates(self) -> WorldAggregates: ...

    def clock(self) -> WorldClock: ...

    def ending(self) -> WorldEnding: ...

    def scenario_progress(self) -> ScenarioProgress: ...

    def latest_actions(self) -> LatestActions: ...

    def people_register(self) -> PeopleRegister: ...

    def attempt_apart(self, work: Callable[[], None]) -> RefusalCode | AcceptedApart: ...

    def commit(self) -> tuple[DomainEvent, ...]: ...

    def roll_back(self) -> None: ...


class AggregateWithMemento(Protocol):
    def memento(self) -> object: ...


class WorldStore(Protocol):
    def start_world(self, aggregates: Iterable[AggregateWithMemento]) -> None: ...

    def session(self) -> WorldSession: ...
