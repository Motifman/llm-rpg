"""本番runtimeの食料劣化確定境界配線。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


def test_runtime_injects_food_spoilage_scope_from_shared_store() -> None:
    """腐る食料があるruntimeは共有store由来の専用scopeへstageを接続する。"""
    runtime = create_world_runtime(
        Path("data/scenarios/survival_island_v2_short.json")
    )

    stage = runtime._simulation_service._food_spoilage_stage
    assert stage is not None
    assert stage._command_scope_factory is not None
    transaction_factory = stage._command_scope_factory._transaction_factory
    assert transaction_factory._data_store is runtime._item_repo._data_store
