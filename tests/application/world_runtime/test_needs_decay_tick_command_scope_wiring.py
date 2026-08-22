"""本番runtimeがneeds decayを独立した確定境界へ接続することを保証する。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


def test_world_runtime_injects_shared_player_status_tick_scope() -> None:
    """needs decayと状態異常は同じprovider構成のscope factoryを共有する。"""
    runtime = create_world_runtime(
        Path("data/scenarios/survival_island_v2_short.json")
    )

    needs_stage = runtime._simulation_service._needs_decay_stage
    status_effects_stage = runtime._simulation_service._status_effects_stage
    assert needs_stage is not None
    assert status_effects_stage is not None
    assert needs_stage._command_scope_factory is not None
    assert needs_stage._command_scope_factory is status_effects_stage._command_scope_factory
    assert needs_stage._event_publisher is None
