"""Step 7: SpotGraphSimulationApplicationService のスモークテスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.application.world_graph.exceptions import (
    SpotGraphPostTickHookFailedException,
    SpotGraphSimulationException,
)
from ai_rpg_world.application.world_graph.spot_graph_simulation_application_service import (
    SpotGraphSimulationApplicationService,
)
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import InMemoryGameTimeProvider
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class _RecordingTravelStage:
    def __init__(self) -> None:
        self.ticks: list[WorldTick] = []

    def run(self, current_tick: WorldTick) -> None:
        self.ticks.append(current_tick)


class _RecordingStage:
    def __init__(self, label: str, order: list[str]) -> None:
        self.label = label
        self.order = order
        self.ticks: list[WorldTick] = []

    def run(self, current_tick: WorldTick) -> None:
        self.order.append(self.label)
        self.ticks.append(current_tick)


class _DomainFailingTravelStage:
    def run(self, current_tick: WorldTick) -> None:
        raise DomainException(f"domain failed at {current_tick.value}")


class _RuntimeFailingTravelStage:
    def run(self, current_tick: WorldTick) -> None:
        raise RuntimeError(f"runtime failed at {current_tick.value}")


class _RecordingLlmTurnTrigger:
    def __init__(self) -> None:
        self.calls = 0

    def run_scheduled_turns(self) -> None:
        self.calls += 1


class _FailingLlmTurnTrigger:
    def __init__(self) -> None:
        self.calls = 0

    def run_scheduled_turns(self) -> None:
        self.calls += 1
        raise RuntimeError("llm failed")


class _RecordingReflectionRunner:
    def __init__(self) -> None:
        self.ticks: list[WorldTick] = []

    def run_after_tick(self, current_tick: WorldTick) -> None:
        self.ticks.append(current_tick)


class _FailingReflectionRunner:
    def __init__(self) -> None:
        self.ticks: list[WorldTick] = []

    def run_after_tick(self, current_tick: WorldTick) -> None:
        self.ticks.append(current_tick)
        raise RuntimeError("reflection failed")


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


def test_spot_graph_simulation_runs_post_tick_hooks() -> None:
    llm_turn_trigger = _RecordingLlmTurnTrigger()
    reflection_runner = _RecordingReflectionRunner()
    sim = SpotGraphSimulationApplicationService(
        time_provider=InMemoryGameTimeProvider(initial_tick=2),
        unit_of_work=InMemoryUnitOfWork(),
        llm_turn_trigger=llm_turn_trigger,  # type: ignore[arg-type]
        reflection_runner=reflection_runner,  # type: ignore[arg-type]
    )

    tick = sim.tick()

    assert tick.value == 3
    assert llm_turn_trigger.calls == 1
    assert [t.value for t in reflection_runner.ticks] == [3]


def test_spot_graph_simulation_runs_travel_event_environment_in_order() -> None:
    order: list[str] = []
    travel_stage = _RecordingStage("travel", order)
    scenario_stage = _RecordingStage("scenario_event", order)
    environment_stage = _RecordingStage("environment", order)
    sim = SpotGraphSimulationApplicationService(
        time_provider=InMemoryGameTimeProvider(initial_tick=4),
        unit_of_work=InMemoryUnitOfWork(),
        travel_stage=travel_stage,  # type: ignore[arg-type]
        scenario_event_stage=scenario_stage,  # type: ignore[arg-type]
        environment_stage=environment_stage,  # type: ignore[arg-type]
    )
    tick = sim.tick()
    assert tick.value == 5
    assert order == ["travel", "scenario_event", "environment"]


def test_spot_graph_simulation_wraps_domain_exception() -> None:
    sim = SpotGraphSimulationApplicationService(
        time_provider=InMemoryGameTimeProvider(initial_tick=0),
        unit_of_work=InMemoryUnitOfWork(),
        travel_stage=_DomainFailingTravelStage(),  # type: ignore[arg-type]
    )

    with pytest.raises(SpotGraphSimulationException, match="domain failed at 1"):
        sim.tick()


def test_spot_graph_simulation_wraps_unexpected_exception() -> None:
    sim = SpotGraphSimulationApplicationService(
        time_provider=InMemoryGameTimeProvider(initial_tick=0),
        unit_of_work=InMemoryUnitOfWork(),
        travel_stage=_RuntimeFailingTravelStage(),  # type: ignore[arg-type]
    )

    with pytest.raises(SystemErrorException, match="spot_graph_tick failed: runtime failed at 1"):
        sim.tick()


def test_spot_graph_simulation_post_tick_failures_run_remaining_hooks_and_raise() -> None:
    llm_turn_trigger = _FailingLlmTurnTrigger()
    reflection_runner = _FailingReflectionRunner()
    sim = SpotGraphSimulationApplicationService(
        time_provider=InMemoryGameTimeProvider(initial_tick=10),
        unit_of_work=InMemoryUnitOfWork(),
        llm_turn_trigger=llm_turn_trigger,  # type: ignore[arg-type]
        reflection_runner=reflection_runner,  # type: ignore[arg-type]
    )

    with pytest.raises(SpotGraphPostTickHookFailedException) as exc_info:
        sim.tick()

    exc = exc_info.value
    assert exc.current_tick.value == 11
    assert exc.failed_hooks == ("llm_turn_trigger", "reflection_runner")
    assert llm_turn_trigger.calls == 1
    assert [t.value for t in reflection_runner.ticks] == [11]
