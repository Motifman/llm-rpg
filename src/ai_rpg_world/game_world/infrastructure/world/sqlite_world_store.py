from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar, cast, final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent
from ai_rpg_world.game_world.domain.condition.aggregate_readings import (
    GroupMembershipReading,
    LatestActionsReading,
    PassageStatesReading,
    PeopleRegisterReading,
    PersonOutcomesReading,
    ScenarioProgressReading,
    SpotAtmospheresReading,
    WeatherReading,
    WhereaboutsReading,
    WorldClockReading,
    WorldFlagsReading,
    WorldStageReading,
)
from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration, NoDayNight, NoWeather
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.exception.world_contents_exception import AggregateNotInWorldException
from ai_rpg_world.game_world.domain.people import PeopleRegister, PeopleRegisterMemento
from ai_rpg_world.game_world.domain.person import (
    GroupMembership,
    GroupMembershipMemento,
    PersonOutcomes,
    PersonOutcomesMemento,
)
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import (
    PassageStates,
    PassageStatesMemento,
    SpotAtmospheres,
    SpotAtmospheresMemento,
    Whereabouts,
    WhereaboutsMemento,
)
from ai_rpg_world.game_world.domain.world_progress import (
    Weather,
    WeatherMemento,
    WorldClock,
    WorldClockMemento,
    WorldEnding,
    WorldEndingMemento,
    WorldStage,
    WorldStageMemento,
)
from ai_rpg_world.game_world.domain.world_records import (
    LatestActions,
    LatestActionsMemento,
    ScenarioProgress,
    ScenarioProgressMemento,
    WorldFlags,
    WorldFlagsMemento,
)
from ai_rpg_world.game_world.infrastructure.persistence.aggregate_codecs import GAME_WORLD_CODECS, StoredMemento
from ai_rpg_world.game_world.infrastructure.world.stored_world_exception import (
    StoredWorldMismatchException,
    WorldSessionEndedException,
    WorldSessionStillOpenException,
)

STORAGE_VERSION = 1

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS world (
        world_id TEXT PRIMARY KEY,
        scenario TEXT NOT NULL,
        scenario_hash TEXT NOT NULL,
        storage_version INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS world_state (
        kind TEXT NOT NULL,
        key TEXT NOT NULL,
        version INTEGER NOT NULL,
        state TEXT NOT NULL,
        PRIMARY KEY (kind, key)
    )""",
)

_Memento = TypeVar("_Memento")
_Aggregate = TypeVar("_Aggregate", bound="_Remembered")


class _Remembered(Protocol):
    def memento(self) -> object: ...


@final
@dataclass(frozen=True)
class _OpenedWorld:
    world_id: WorldId
    design: WorldDesign
    random: RandomSource
    declares_world_stages: bool

    @property
    def key(self) -> str:
        return self.world_id.value

    @classmethod
    def of(cls, world_id: WorldId, design: WorldDesign, random: RandomSource) -> _OpenedWorld:
        return cls(world_id, design, random, not isinstance(design.initial_world().stage, NoWorldStages))

    def with_nouns(
        self, from_memento: Callable[[_Memento, DeclaredNouns], _Aggregate]
    ) -> Callable[[_Memento], _Aggregate]:
        nouns = self.design.nouns
        return lambda memento: from_memento(memento, nouns)


@final
class SqliteWorldStore:
    def __init__(self, connection: sqlite3.Connection, world: _OpenedWorld) -> None:
        self._connection = connection
        self._world = world

    @classmethod
    def create(
        cls,
        path: Path | str,
        *,
        world_id: WorldId,
        scenario: str,
        scenario_hash: str,
        design: WorldDesign,
        random: RandomSource,
    ) -> SqliteWorldStore:
        connection = _connected(path)
        if connection.execute("SELECT COUNT(*) FROM world").fetchone()[0] != 0:
            connection.close()
            raise StoredWorldMismatchException(f"{path} already holds a world")
        connection.execute(
            "INSERT INTO world (world_id, scenario, scenario_hash, storage_version) VALUES (?, ?, ?, ?)",
            (world_id.value, scenario, scenario_hash, STORAGE_VERSION),
        )
        return cls(connection, _OpenedWorld.of(world_id, design, random))

    @classmethod
    def open(
        cls, path: Path | str, *, scenario_hash: str, design: WorldDesign, random: RandomSource
    ) -> SqliteWorldStore:
        connection = _connected(path)
        rows = connection.execute("SELECT world_id, scenario_hash, storage_version FROM world").fetchall()
        try:
            if len(rows) != 1:
                raise StoredWorldMismatchException(f"{path} holds {len(rows)} worlds, not 1")
            world_id, stored_hash, stored_version = rows[0]
            if stored_version != STORAGE_VERSION:
                raise StoredWorldMismatchException(
                    f"{path} was written in storage version {stored_version}, but this code reads {STORAGE_VERSION}"
                )
            if stored_hash != scenario_hash:
                raise StoredWorldMismatchException(f"{path} was opened with a scenario whose content differs")
        except StoredWorldMismatchException:
            connection.close()
            raise
        return cls(connection, _OpenedWorld.of(WorldId(world_id), design, random))

    def session(self) -> SqliteWorldSession:
        if self._connection.in_transaction:
            raise WorldSessionStillOpenException("the previous session was neither committed nor rolled back")
        return SqliteWorldSession(self._connection, self._world)

    def close(self) -> None:
        self._connection.close()


def _connected(path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    for statement in _SCHEMA:
        connection.execute(statement)
    return connection


@final
@dataclass
class _HeldAggregate:
    aggregate: _Remembered
    read_state: str


@final
class SqliteWorldSession:
    def __init__(self, connection: sqlite3.Connection, world: _OpenedWorld) -> None:
        self._connection = connection
        self._world = world
        self._held: dict[tuple[str, str], _HeldAggregate] = {}
        self._in_scope = True
        connection.execute("BEGIN")

    def facts(self) -> _SqliteWorldFacts:
        return _SqliteWorldFacts(self, self.aggregates(), self._world)

    def aggregates(self) -> _SqliteWorldAggregates:
        return _SqliteWorldAggregates(self, self._world)

    def clock(self) -> WorldClock:
        return self.held_aggregate(WorldClockMemento, self._world.key, WorldClock.from_memento)

    def ending(self) -> WorldEnding:
        return self.held_aggregate(WorldEndingMemento, self._world.key, WorldEnding.from_memento)

    def scenario_progress(self) -> ScenarioProgress:
        return self.held_aggregate(ScenarioProgressMemento, self._world.key, ScenarioProgress.from_memento)

    def latest_actions(self) -> LatestActions:
        return self.held_aggregate(LatestActionsMemento, self._world.key, LatestActions.from_memento)

    def people_register(self) -> PeopleRegister:
        return self.held_aggregate(
            PeopleRegisterMemento, self._world.key, self._world.with_nouns(PeopleRegister.from_memento)
        )

    def commit(self) -> tuple[DomainEvent, ...]:
        self._require_in_scope()
        self._in_scope = False
        try:
            for (kind, key), held in self._held.items():
                stored = GAME_WORLD_CODECS.stored(held.aggregate.memento())
                if stored.state == held.read_state:
                    continue
                self._connection.execute(
                    "UPDATE world_state SET version = ?, state = ? WHERE kind = ? AND key = ?",
                    (stored.version, stored.state, kind, key),
                )
            self._connection.execute("COMMIT")
        except BaseException:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise
        emitters = [held.aggregate for held in self._held.values() if isinstance(held.aggregate, AggregateRoot)]
        events = sorted((event for emitter in emitters for event in emitter.get_events()), key=lambda e: e.sequence)
        self._held.clear()
        return tuple(events)

    def roll_back(self) -> None:
        self._require_in_scope()
        self._in_scope = False
        self._connection.execute("ROLLBACK")
        self._held.clear()

    def held_aggregate(
        self, memento_type: type[_Memento], key: str, from_memento: Callable[[_Memento], _Aggregate]
    ) -> _Aggregate:
        self._require_in_scope()
        kind = GAME_WORLD_CODECS.kind_of(memento_type)
        held = self._held.get((kind, key))
        if held is not None:
            return cast(_Aggregate, held.aggregate)
        row = self._connection.execute(
            "SELECT version, state FROM world_state WHERE kind = ? AND key = ?", (kind, key)
        ).fetchone()
        if row is None:
            raise AggregateNotInWorldException(f"this world holds no {kind} for {key}")
        version, state = row
        aggregate = from_memento(GAME_WORLD_CODECS.memento(StoredMemento(kind, version, state), memento_type))
        self._held[(kind, key)] = _HeldAggregate(aggregate, state)
        return aggregate

    def _require_in_scope(self) -> None:
        if not self._in_scope:
            raise WorldSessionEndedException("this session has already been committed or rolled back")


@final
class _SqliteWorldFacts:
    def __init__(self, session: SqliteWorldSession, aggregates: _SqliteWorldAggregates, world: _OpenedWorld) -> None:
        self._session = session
        self._aggregates = aggregates
        self._world = world

    def now(self) -> WorldTick:
        return self._session.clock().now()

    def rules(self) -> WorldRules:
        return self._world.design.world_rules

    def day_night(self) -> DayNightDeclaration | NoDayNight:
        return self._world.design.day_night

    def nouns(self) -> DeclaredNouns:
        return self._world.design.nouns

    def random(self) -> RandomSource:
        return self._world.random

    def people(self) -> tuple[PersonId, ...]:
        return tuple(character.person_id for character in self._world.design.nouns.all_characters())

    def people_register(self) -> PeopleRegisterReading:
        return self._session.people_register()

    def whereabouts(self) -> WhereaboutsReading:
        return self._aggregates.whereabouts()

    def passages(self) -> PassageStatesReading:
        return self._aggregates.passages()

    def atmospheres(self) -> SpotAtmospheresReading:
        return self._aggregates.atmospheres()

    def outcomes(self) -> PersonOutcomesReading:
        return self._aggregates.outcomes()

    def membership(self) -> GroupMembershipReading:
        return self._aggregates.membership()

    def clock(self) -> WorldClockReading:
        return self._session.clock()

    def weather(self) -> WeatherReading | NoWeather:
        if isinstance(self._world.design.weather, NoWeather):
            return NoWeather()
        return self._aggregates.weather()

    def world_stage(self) -> WorldStageReading | NoWorldStages:
        if not self._world.declares_world_stages:
            return NoWorldStages()
        return self._aggregates.world_stage()

    def flags(self) -> WorldFlagsReading:
        return self._aggregates.flags()

    def scenario_progress(self) -> ScenarioProgressReading:
        return self._session.scenario_progress()

    def latest_actions(self) -> LatestActionsReading:
        return self._session.latest_actions()


@final
class _SqliteWorldAggregates:
    def __init__(self, session: SqliteWorldSession, world: _OpenedWorld) -> None:
        self._session = session
        self._world = world

    def flags(self) -> WorldFlags:
        return self._session.held_aggregate(WorldFlagsMemento, self._world.key, WorldFlags.from_memento)

    def passages(self) -> PassageStates:
        return self._session.held_aggregate(
            PassageStatesMemento, self._world.key, self._world.with_nouns(PassageStates.from_memento)
        )

    def atmospheres(self) -> SpotAtmospheres:
        return self._session.held_aggregate(
            SpotAtmospheresMemento, self._world.key, self._world.with_nouns(SpotAtmospheres.from_memento)
        )

    def whereabouts(self) -> Whereabouts:
        return self._session.held_aggregate(
            WhereaboutsMemento, self._world.key, self._world.with_nouns(Whereabouts.from_memento)
        )

    def outcomes(self) -> PersonOutcomes:
        return self._session.held_aggregate(
            PersonOutcomesMemento, self._world.key, self._world.with_nouns(PersonOutcomes.from_memento)
        )

    def membership(self) -> GroupMembership:
        return self._session.held_aggregate(
            GroupMembershipMemento, self._world.key, self._world.with_nouns(GroupMembership.from_memento)
        )

    def world_stage(self) -> WorldStage:
        if not self._world.declares_world_stages:
            raise AggregateNotInWorldException("this world declares no world stages")
        return self._session.held_aggregate(WorldStageMemento, self._world.key, WorldStage.from_memento)

    def weather(self) -> Weather:
        if isinstance(self._world.design.weather, NoWeather):
            raise AggregateNotInWorldException("this world declares no weather")
        return self._session.held_aggregate(WeatherMemento, self._world.key, Weather.from_memento)
