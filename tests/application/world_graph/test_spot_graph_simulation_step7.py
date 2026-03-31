"""Step 7: SpotGraphSimulationApplicationService のスモークテスト。"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_graph_simulation_application_service import (
    SpotGraphSimulationApplicationService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import InMemoryGameTimeProvider
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class _RecordingTravelStage:
    def __init__(self) -> None:
        self.ticks: list[WorldTick] = []

    def run(self, current_tick: WorldTick) -> None:
        self.ticks.append(current_tick)


def test_spot_graph_simulation_advances_time_and_runs_travel_stage() -> None:
    time_provider = InMemoryGameTimeProvider(initial_tick=5)
    travel = _RecordingTravelStage()
    uow = InMemoryUnitOfWork()
    sim = SpotGraphSimulationApplicationService(
        time_provider=time_provider,
        unit_of_work=uow,
        travel_stage=travel,  # type: ignore[arg-type]
    )

    tick = sim.tick()

    assert tick.value == 6
    assert time_provider.get_current_tick().value == 6
    assert len(travel.ticks) == 1
    assert travel.ticks[0].value == 6


def test_spot_graph_simulation_without_travel_stage() -> None:
    time_provider = InMemoryGameTimeProvider(initial_tick=0)
    uow = InMemoryUnitOfWork()
    sim = SpotGraphSimulationApplicationService(
        time_provider=time_provider,
        unit_of_work=uow,
        travel_stage=None,
    )
    tick = sim.tick()
    assert tick.value == 1
