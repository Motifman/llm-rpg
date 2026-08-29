"""本番runtimeがmonster spawnをslot単位の確定境界へ接続する契約。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


def test_runtime_injects_monster_spawn_scope_and_shared_loadout_store() -> None:
    """条件付きmonster配置はscopeを使い、loadoutも共有storeへ保存する。"""
    runtime = create_world_runtime(
        Path("data/scenarios/survival_island_v2_short.json")
    )

    stage = runtime._simulation_service._monster_spawn_stage
    assert stage is not None
    assert stage._command_scope_factory is not None
    shared_store = stage._monster_repository._data_store
    assert stage._skill_loadout_repository._data_store is shared_store
    transaction_factory = stage._command_scope_factory._transaction_factory
    assert transaction_factory._transaction_factory._data_store is shared_store
