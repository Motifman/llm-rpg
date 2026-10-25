"""本番runtimeの食料劣化確定境界配線。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.spoilage import STATE_KEY_ACQUIRED_AT_TICK


def test_runtime_injects_food_spoilage_scope_from_shared_store() -> None:
    """腐る食料があるruntimeは共有store由来の専用scopeへstageを接続する。"""
    runtime = create_world_runtime(Path("data/scenarios/survival_island_v2_short.json"))

    stage = runtime._simulation_service._food_spoilage_stage
    assert stage is not None
    assert stage._command_scope_factory is not None
    transaction_factory = stage._command_scope_factory._transaction_factory
    assert transaction_factory._data_store is runtime._item_repo._data_store


def test_runtime_collects_spoiled_event_into_daily_buffer_after_commit() -> None:
    """本番専用dispatcherは腐敗eventを確定後に日次観測バッファへ渡す。"""
    runtime = create_world_runtime(Path("data/scenarios/survival_island_v2_short.json"))
    stage = runtime._simulation_service._food_spoilage_stage
    assert stage is not None
    spec_id, threshold = stage._spoilable[0]
    spec = runtime._item_spec_repo.find_by_id(spec_id)
    assert spec is not None
    item = ItemAggregate.create(
        item_instance_id=ItemInstanceId(999_901),
        item_spec=spec,
        quantity=1,
        state={STATE_KEY_ACQUIRED_AT_TICK: -threshold},
    )
    runtime._item_repo.save(item)

    stage.run(WorldTick(runtime.current_tick()))

    assert runtime._pending_spoiled[spec_id.value] == {
        "spec_id": spec_id.value,
        "spec_name": spec.name,
        "instance_ids": [999_901],
    }
    assert not hasattr(runtime, "_append_food_spoiled_observation")
