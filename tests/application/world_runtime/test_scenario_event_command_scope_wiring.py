"""本番runtimeがscenario eventをevent定義単位の確定境界へ接続する契約。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


def test_world_runtime_injects_scenario_event_command_scope() -> None:
    """出荷scenarioのscenario event stageへ専用scope factoryを必ず注入する。"""
    runtime = create_world_runtime(
        Path("data/scenarios/survival_island_v2_short.json")
    )

    stage = runtime._scenario_event_stage
    assert stage._command_scope_factory is not None
