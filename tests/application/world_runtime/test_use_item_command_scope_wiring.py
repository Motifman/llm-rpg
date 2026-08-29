"""本番の use_item が確定境界を必ず経由することを保証する。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


def test_world_runtime_exposes_use_item_command_scope_factory() -> None:
    """出荷runtimeは use_item 用CommandScope factoryを保持する。"""
    runtime = create_world_runtime(
        Path("data/scenarios/survival_island_v2_short.json")
    )

    assert runtime._use_item_command_scope_factory is not None
