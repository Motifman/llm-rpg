"""本番runtimeの取引提案期限切れ確定境界配線。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


def test_runtime_injects_offer_expiry_scope_for_shared_stores() -> None:
    """期限切れstageは共有data storeとpending offer storeを同じscopeへ載せる。"""
    runtime = create_world_runtime(
        Path("data/scenarios/survival_island_v2_short.json")
    )

    stage = runtime._simulation_service._trade_offer_expiry_stage
    scope_factory = stage._command_scope_factory
    assert scope_factory is not None
    transaction_factory = scope_factory._transaction_factory
    assert transaction_factory._transaction_factory._data_store is (
        runtime._item_repo._data_store
    )
    participant = transaction_factory._participants[0]
    assert participant.rollback_resource is runtime._pending_trade_offer_store
