"""本番weather / day-night stageの確定境界配線。"""

from pathlib import Path

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    TimeOfDayChangedEvent,
)


SCENARIO = Path("data/scenarios/survival_island_v2.json")


def test_runtime_wires_weather_and_day_night_to_separate_command_scopes() -> None:
    """天候と昼夜は同じstore由来の別々の遷移scopeへ接続される。"""
    runtime = create_world_runtime(SCENARIO)
    weather = runtime._environment_stage
    day_night = runtime._day_night_stage

    assert weather._command_scope_factory is not None
    assert day_night is not None
    assert day_night._command_scope_factory is not None
    assert weather._command_scope_factory is not day_night._command_scope_factory
    weather_transaction = weather._command_scope_factory._transaction_factory
    day_night_transaction = day_night._command_scope_factory._transaction_factory
    assert (
        weather_transaction._transaction_factory._data_store
        is runtime._spot_interior_repo._data_store
    )
    assert (
        day_night_transaction._transaction_factory._data_store
        is runtime._spot_interior_repo._data_store
    )


def test_same_scenario_seed_creates_same_weather_random_stream() -> None:
    """同じ実験seedから作ったruntimeは、条件評価と独立した同じ天候乱数列を持つ。"""
    config = ResolvedLlmRuntimeConfig.for_tests(scenario_random_seed=182)

    first = create_world_runtime(SCENARIO, config=config)
    second = create_world_runtime(SCENARIO, config=config)

    assert (
        first._environment_stage.random_state()
        == second._environment_stage.random_state()
    )
    assert (
        first._environment_stage.random_state()
        != first._scenario_predicate_random.getstate()
    )


def test_runtime_weather_dispatcher_observes_committed_transition(monkeypatch) -> None:
    """本番天候dispatcherはscope確定後にruntimeの観測入口を一度呼ぶ。"""
    runtime = create_world_runtime(SCENARIO)
    observed = []
    monkeypatch.setattr(runtime, "_append_weather_observation", observed.append)

    runtime._environment_stage.run(WorldTick(25))

    assert observed == [runtime._environment_stage.rollback_snapshot()[0]]


def test_runtime_day_night_dispatcher_publishes_committed_event(monkeypatch) -> None:
    """本番昼夜dispatcherはscope確定後に既存の昼夜観測eventを一度配送する。"""
    runtime = create_world_runtime(SCENARIO)
    delivered = []
    monkeypatch.setattr(
        runtime._speech_event_publisher,
        "publish_all",
        lambda events: delivered.extend(events),
    )
    day_night = runtime._day_night_stage
    assert day_night is not None

    day_night.run(WorldTick(12))

    assert len(delivered) == 1
    assert isinstance(delivered[0], TimeOfDayChangedEvent)
    assert delivered[0].old_phase_name == "morning"
    assert delivered[0].new_phase_name == "noon"
