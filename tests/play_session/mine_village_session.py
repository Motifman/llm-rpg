from __future__ import annotations

from functools import cache
from pathlib import Path

from ai_rpg_world.being.application.enter_environment import EnterEnvironment
from ai_rpg_world.being.application.prepare_being import PrepareBeing
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import InMemoryAcquaintanceRepository
from ai_rpg_world.being.infrastructure.in_memory_being_repository import InMemoryBeingRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.game_world.application.brief_entering_person import BriefEnteringPerson
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.domain.value_object import WorldId
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario, load_scenario
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from ai_rpg_world.play_session.application.start_play_session import StartPlaySession, StartPlaySessionCommand
from ai_rpg_world.play_session.domain.cast import BeingCastInWorldEvent
from ai_rpg_world.play_session.infrastructure.in_memory_cast_repository import InMemoryCastRepository
from ai_rpg_world.play_session.infrastructure.roles_from_scenario import casting_by_person_name, roles_from_scenario

_MINE_VILLAGE = Path(__file__).parents[2] / "data" / "scenarios" / "mine_village_v2.yaml"
WORLD = WorldId("mine_village_v2#1")
ENVIRONMENT_NAME = "廃坑の山村"


@cache
def _scenario() -> LoadedScenario:
    return load_scenario(_MINE_VILLAGE)


class MineVillageSession:
    """廃坑の山村 v2 を開き、4 人の Being を用意して入れたところ。"""

    def __init__(self, *, without: tuple[str, ...] = ()) -> None:
        scenario = _scenario()
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=WORLD,
            scenario="mine_village_v2",
            scenario_hash="mine_village_v2",
            design=scenario.design,
            random=SeedableRandomSource(0),
        )
        self.beings = InMemoryBeingRepository()
        self.acquaintances = InMemoryAcquaintanceRepository()
        self.clock = InMemoryMemoryTurnClock()
        self.cast_events: list[BeingCastInWorldEvent] = []
        self.casts = InMemoryCastRepository(handoff=self.cast_events.extend)
        self.start = StartPlaySession(
            open_world=OpenWorld(self.store),
            brief=BriefEnteringPerson(scenario.design),
            prepare_being=PrepareBeing(self.beings),
            enter_environment=EnterEnvironment(self.beings, self.acquaintances, self.clock),
            casts=self.casts,
        )
        self.command = StartPlaySessionCommand(
            open_world=OpenWorldCommand(world_id=WORLD, design=scenario.design),
            environment_name=ENVIRONMENT_NAME,
            roles=tuple(role for role in roles_from_scenario(scenario) if role.person.value not in without),
            casting=casting_by_person_name(scenario),
        )

    def started(self) -> MineVillageSession:
        self.start(self.command)
        return self
