"""本番weather / day-night stageの確定境界配線。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


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
