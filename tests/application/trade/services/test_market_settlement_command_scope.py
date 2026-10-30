"""複数注文をまたぐ市場約定を一操作で確定する契約。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.trade.services.in_memory_market_board_store import (
    InMemoryMarketBoardStore,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MarketBoardActivityEvent,
    MarketDeliveryLeftAtBoardEvent,
)

_SCENARIO = Path("data/scenarios/market_town_v3_board.json")
_PLAYER = PlayerId(1)


class _TraceRecorder:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(self, kind, **payload) -> None:
        if kind is TraceEventKind.MARKET_ACTIVITY:
            self.entries.append(dict(payload))


def _runtime() -> Any:
    return create_world_runtime(_SCENARIO)


def _spec_id(runtime: Any, label: str) -> ItemSpecId:
    return runtime._item_spec_repo.find_by_name(label).item_spec_id


def _held(runtime: Any, label: str) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(_PLAYER)
    return count_owned_item_instances_by_spec(
        inventory,
        runtime._item_repo,
    ).get(_spec_id(runtime, label), 0)


def _give(runtime: Any, label: str, quantity: int) -> None:
    grant_item_specs_to_inventory(
        _PLAYER,
        tuple(_spec_id(runtime, label) for _ in range(quantity)),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _gold(runtime: Any) -> int:
    return runtime._player_status_repo.find_by_id(_PLAYER).gold.value


def _item_ids(runtime: Any) -> tuple[int, ...]:
    return tuple(sorted(item.item_instance_id.value for item in runtime._item_repo.find_all()))


def _capture_observation_and_trace(
    runtime: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[MarketBoardActivityEvent], list[dict[str, Any]]]:
    events: list[MarketBoardActivityEvent] = []
    recorder = _TraceRecorder()
    runtime._market_service._trace = recorder
    runtime._market_service._now = lambda: 1
    original_publish = runtime._speech_event_publisher.publish_all

    def capture(published):
        events.extend(event for event in published if isinstance(event, MarketBoardActivityEvent))
        return original_publish(published)

    monkeypatch.setattr(runtime._speech_event_publisher, "publish_all", capture)
    return events, recorder.entries


def _fail_second_board_save(monkeypatch: pytest.MonkeyPatch) -> None:
    original_save = InMemoryMarketBoardStore.save
    calls = 0

    def fail_second(self, board):
        nonlocal calls
        calls += 1
        original_save(self, board)
        if calls == 2:
            raise RuntimeError("second market settlement failed")

    monkeypatch.setattr(InMemoryMarketBoardStore, "save", fail_second)


def _fail_first_board_save(monkeypatch: pytest.MonkeyPatch) -> None:
    original_save = InMemoryMarketBoardStore.save

    def fail_after_save(self, board):
        original_save(self, board)
        raise RuntimeError("market settlement failed")

    monkeypatch.setattr(InMemoryMarketBoardStore, "save", fail_after_save)


def test_buy_best_second_settlement_failure_rolls_back_every_settlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """複数出品の2件目失敗は全注文・gold・受取品・観測・traceを戻す。"""
    runtime = _runtime()
    status = runtime._player_status_repo.find_by_id(_PLAYER)
    status.earn_gold(100)
    runtime._player_status_repo.save(status)
    before_gold = _gold(runtime)
    before_board = runtime._market_service.board()
    before_items = _item_ids(runtime)
    events, traces = _capture_observation_and_trace(runtime, monkeypatch)
    _fail_second_board_save(monkeypatch)

    with pytest.raises(RuntimeError, match="second market settlement failed"):
        runtime._market_service.buy_best(
            _PLAYER,
            item_label="焼きたてのパン",
            quantity=2,
            current_tick=1,
        )

    assert runtime._market_service.board() == before_board
    assert _gold(runtime) == before_gold
    assert _held(runtime, "焼きたてのパン") == 0
    assert _item_ids(runtime) == before_items
    assert events == []
    assert traces == []


def test_sell_best_second_settlement_failure_rolls_back_every_settlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """複数買い注文の2件目失敗は全注文・品・gold・観測・traceを戻す。"""
    runtime = _runtime()
    herb = _spec_id(runtime, "薬草")
    runtime._market_service.place_merchant_buy_order(
        merchant_id=1,
        item_spec_id=herb.value,
        quantity=1,
        unit_price=14,
        current_tick=0,
    )
    _give(runtime, "薬草", 3)
    before_gold = _gold(runtime)
    before_board = runtime._market_service.board()
    before_items = _item_ids(runtime)
    events, traces = _capture_observation_and_trace(runtime, monkeypatch)
    _fail_second_board_save(monkeypatch)

    with pytest.raises(RuntimeError, match="second market settlement failed"):
        runtime._market_service.sell_best(
            _PLAYER,
            item_label="薬草",
            quantity=3,
            current_tick=1,
        )

    assert runtime._market_service.board() == before_board
    assert _gold(runtime) == before_gold
    assert _held(runtime, "薬草") == 3
    assert _item_ids(runtime) == before_items
    assert events == []
    assert traces == []


def test_failed_delivery_rolls_back_item_left_at_market_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """満杯の買い手へ配送後に失敗しても板の足元へ品と観測を残さない。"""
    runtime = _runtime()
    buyer = PlayerId(2)
    buyer_status = runtime._player_status_repo.find_by_id(buyer)
    buyer_status.earn_gold(100)
    runtime._player_status_repo.save(buyer_status)
    runtime._market_service.place_buy_order(
        buyer,
        item_label="薬草",
        quantity=1,
        unit_price=20,
        current_tick=1,
    )
    bread = _spec_id(runtime, "焼きたてのパン")
    inventory = runtime._player_inventory_repo.find_by_id(buyer)
    while not inventory.is_inventory_full():
        grant_item_specs_to_inventory(
            buyer,
            (bread,),
            runtime._item_repo,
            runtime._item_spec_repo,
            runtime._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )
        inventory = runtime._player_inventory_repo.find_by_id(buyer)
    _give(runtime, "薬草", 1)
    board_spot = runtime._market_service.board_spot_id
    before_interior = runtime._spot_interior_repo.find_by_spot_id(board_spot)
    before_ground = before_interior.ground_items
    before_board = runtime._market_service.board()
    delivered: list[object] = []
    original_publish = runtime._speech_event_publisher.publish_all

    def capture(events):
        delivered.extend(
            event
            for event in events
            if isinstance(
                event,
                (MarketBoardActivityEvent, MarketDeliveryLeftAtBoardEvent),
            )
        )
        return original_publish(events)

    monkeypatch.setattr(runtime._speech_event_publisher, "publish_all", capture)
    _fail_first_board_save(monkeypatch)

    with pytest.raises(RuntimeError, match="market settlement failed"):
        runtime._market_service.sell_best(
            _PLAYER,
            item_label="薬草",
            quantity=1,
            current_tick=2,
        )

    after_interior = runtime._spot_interior_repo.find_by_spot_id(board_spot)
    assert after_interior.ground_items == before_ground
    assert runtime._market_service.board() == before_board
    assert _held(runtime, "薬草") == 1
    assert delivered == []
