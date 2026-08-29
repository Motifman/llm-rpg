"""本番runtimeの市場注文期限切れ確定境界配線。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


def test_runtime_injects_market_expiry_scope_for_shared_stores() -> None:
    """期限切れstageは共有data storeと市場板を同じscopeへ載せる。"""
    runtime = create_world_runtime(Path("data/scenarios/market_town_v3_board.json"))

    stage = runtime._simulation_service._market_order_expiry_stage
    scope_factory = stage._command_scope_factory
    assert scope_factory is not None
    transaction_factory = scope_factory._transaction_factory
    assert transaction_factory._transaction_factory._data_store is (
        runtime._item_repo._data_store
    )
    participant = transaction_factory._participants[0]
    assert participant.rollback_resource is runtime._market_board_store
