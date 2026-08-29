"""本番reactive stagesが共有確定境界へ接続される契約。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


SCENARIO = Path("data/scenarios/relay_puzzle_demo.json")


def test_runtime_wires_object_and_passage_to_same_scope_factory() -> None:
    """objectとpassageは同じgraph・乱数所有権を持つscope factoryを共有する。"""
    runtime = create_world_runtime(SCENARIO)
    simulation = runtime._simulation_service
    object_stage = simulation._reactive_object_state_stage
    passage_stage = simulation._reactive_binding_stage

    assert object_stage._command_scope_factory is not None
    assert passage_stage._command_scope_factory is object_stage._command_scope_factory
    transaction_factory = object_stage._command_scope_factory._transaction_factory
    assert (
        transaction_factory._transaction_factory._data_store
        is runtime._spot_interior_repo._data_store
    )
