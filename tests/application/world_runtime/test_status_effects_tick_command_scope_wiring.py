"""本番world runtimeが状態異常tickを独立した確定境界へ接続することを保証する。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


def test_world_runtime_injects_status_effects_tick_command_scope() -> None:
    """出荷scenarioの状態異常更新にCommandScope factoryを必ず注入する。"""
    runtime = create_world_runtime(
        Path("data/scenarios/survival_island_v2_short.json")
    )

    stage = runtime._simulation_service._status_effects_stage
    assert stage is not None
    assert stage._command_scope_factory is not None
    assert stage._event_publisher is None
