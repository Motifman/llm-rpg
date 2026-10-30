"""本番NPC商人売買が一回の売買を一つの確定単位にする契約。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerTradedWithMerchantEvent,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)

_SCENARIO = Path("data/scenarios/market_town_v1.json")


def _runtime() -> Any:
    return create_world_runtime(_SCENARIO)


def _held(runtime: Any, player_id: PlayerId, spec_id: int) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    return count_owned_item_instances_by_spec(
        inventory,
        runtime._item_repo,
    ).get(ItemSpecId.create(spec_id), 0)


def _capture_events(runtime: Any, monkeypatch: pytest.MonkeyPatch):
    delivered: list[PlayerTradedWithMerchantEvent] = []
    original = runtime._speech_event_publisher.publish_all

    def capture(events):
        delivered.extend(event for event in events if isinstance(event, PlayerTradedWithMerchantEvent))
        return original(events)

    monkeypatch.setattr(runtime._speech_event_publisher, "publish_all", capture)
    return delivered


def test_buy_inventory_failure_rolls_back_gold_items_and_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """購入後半の所持保存失敗は支払・生成品・成功観測をすべて戻す。"""
    runtime = _runtime()
    player_id = runtime.get_player_ids()[0]
    merchant = runtime.scenario.merchants[0]
    entry = merchant.sells[0]
    before_gold = runtime._player_status_repo.find_by_id(player_id).gold.value
    before_items = len(runtime._item_repo.find_all())
    delivered = _capture_events(runtime, monkeypatch)
    original_save = InMemoryPlayerInventoryRepository.save

    def fail_after_save(self, inventory):
        result = original_save(self, inventory)
        raise RuntimeError("merchant buy inventory failed")

    monkeypatch.setattr(InMemoryPlayerInventoryRepository, "save", fail_after_save)

    with pytest.raises(RuntimeError, match="merchant buy inventory failed"):
        runtime._merchant_trade_service.buy(
            player_id,
            merchant_id=merchant.merchant_id,
            item_spec_id=entry.item_spec_id,
            quantity=1,
        )

    assert runtime._player_status_repo.find_by_id(player_id).gold.value == before_gold
    assert len(runtime._item_repo.find_all()) == before_items
    assert _held(runtime, player_id, entry.item_spec_id) == 0
    assert delivered == []


def test_sell_status_failure_rolls_back_item_gold_and_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """売却後半の所持金保存失敗は除去品・所持金・成功観測をすべて戻す。"""
    runtime = _runtime()
    player_id = runtime.get_player_ids()[0]
    merchant = runtime.scenario.merchants[0]
    entry = merchant.buys[0]
    spec_id = ItemSpecId.create(entry.item_spec_id)
    grant_item_specs_to_inventory(
        player_id,
        (spec_id,),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )
    before_gold = runtime._player_status_repo.find_by_id(player_id).gold.value
    delivered = _capture_events(runtime, monkeypatch)
    original_save = InMemoryPlayerStatusRepository.save

    def fail_after_save(self, status):
        result = original_save(self, status)
        raise RuntimeError("merchant sell status failed")

    monkeypatch.setattr(InMemoryPlayerStatusRepository, "save", fail_after_save)

    with pytest.raises(RuntimeError, match="merchant sell status failed"):
        runtime._merchant_trade_service.sell(
            player_id,
            merchant_id=merchant.merchant_id,
            item_spec_id=entry.item_spec_id,
            quantity=1,
        )

    assert _held(runtime, player_id, entry.item_spec_id) == 1
    assert runtime._player_status_repo.find_by_id(player_id).gold.value == before_gold
    assert delivered == []
