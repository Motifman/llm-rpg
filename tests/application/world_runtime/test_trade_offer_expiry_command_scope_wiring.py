"""本番runtimeの取引提案期限切れ確定境界配線。"""

from pathlib import Path

import pytest

from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import PendingTradeOffer
from ai_rpg_world.domain.trade.value_object.trade_side import TradeSide
from ai_rpg_world.domain.world_graph.event.spot_graph_event import PlayerTradeOfferEvent


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


def test_committed_expiry_observation_is_delivered_before_later_offer_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """後続提案が失敗しても、先に確定した期限切れ観測はtick末を待たず届く。"""
    runtime = create_world_runtime(
        Path("data/scenarios/survival_island_v2_short.json")
    )
    store = runtime._pending_trade_offer_store
    first = PendingTradeOffer.create(
        offer_id=store.next_offer_id(),
        offerer_player_id=PlayerId(1),
        target_player_id=PlayerId(2),
        gives=TradeSide(gold=1),
        asks=TradeSide(items=((1, 1),)),
        created_tick=-2,
        expires_in_ticks=1,
    )
    second = PendingTradeOffer.create(
        offer_id=store.next_offer_id(),
        offerer_player_id=PlayerId(3),
        target_player_id=PlayerId(2),
        gives=TradeSide(gold=1),
        asks=TradeSide(items=((1, 1),)),
        created_tick=-2,
        expires_in_ticks=1,
    )
    store.put(first)
    store.put(second)
    graph = runtime._spot_graph_repo.find_graph()
    graph.clear_events()
    for player_id in (PlayerId(1), PlayerId(2), PlayerId(3)):
        runtime._obs_buffer.drain(player_id)

    original_put = store.put

    def fail_after_removing_second(updated: PendingTradeOffer) -> None:
        original_put(updated)
        if updated.offer_id == second.offer_id and not updated.is_pending:
            raise RuntimeError("second expiry failed")

    monkeypatch.setattr(store, "put", fail_after_removing_second)

    with pytest.raises(SystemErrorException, match="second expiry failed"):
        runtime._simulation_service.tick()

    assert store.find(first.offer_id) is None
    assert store.find(second.offer_id) == second
    target_observations = runtime._obs_buffer.drain(PlayerId(2))
    assert any(
        entry.output.structured.get("kind") == "expired"
        for entry in target_observations
    )
    assert not any(
        isinstance(event, PlayerTradeOfferEvent) and event.kind == "expired"
        for event in runtime._spot_graph_repo.find_graph().get_events()
    )
