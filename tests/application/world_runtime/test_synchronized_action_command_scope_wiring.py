"""本番synchronized action resolverの確定境界配線。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


SCENARIO = Path("data/scenarios/station_drill.json")


def test_runtime_wires_resolver_to_group_command_scope() -> None:
    """resolverはworld flag・graphと同じstoreを使うscope factoryへ接続される。"""
    runtime = create_world_runtime(SCENARIO)
    stage = runtime._simulation_service._sync_action_resolver_stage

    assert stage._command_scope_factory is not None
    transaction_factory = stage._command_scope_factory._transaction_factory
    assert (
        transaction_factory._transaction_factory._data_store
        is runtime._spot_interior_repo._data_store
    )
