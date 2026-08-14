"""本番world runtimeがgive_itemを旧repository直書きへ戻さない配線を保証する。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


def test_world_runtime_injects_give_item_command_scope() -> None:
    """出荷scenarioのitem transfer serviceにはCommandScope factoryを必ず注入する。"""
    scenario = Path("data/scenarios/survival_island_v2_short.json")

    runtime = create_world_runtime(scenario)

    assert runtime._item_transfer_service._give_item_command_scope_factory is not None
