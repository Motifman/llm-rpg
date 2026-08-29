"""本番市場注文の掲載・値付け直し・取り下げを一操作で確定する契約。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.trade.services.market_service import (
    MarketGoldNotEnoughError,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MarketBoardActivityEvent,
)
from ai_rpg_world.application.trade.services.in_memory_market_board_store import (
    InMemoryMarketBoardStore,
)
from tests.support.overflow_sinks import IGNORE_OVERFLOW


_SCENARIO = Path("data/scenarios/market_town_v1.json")
_TRADE_SCENARIO = Path("data/scenarios/market_town_v3_board.json")
_PLAYER = PlayerId(1)
_HERB = "薬草"


class _TraceRecorder:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(self, kind, **payload) -> None:
        if kind is TraceEventKind.MARKET_ACTIVITY:
            self.entries.append(dict(payload))


def _runtime() -> Any:
    return create_world_runtime(_SCENARIO)


def _spec_id(runtime: Any) -> ItemSpecId:
    return runtime._item_spec_repo.find_by_name(_HERB).item_spec_id


def _held(runtime: Any) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(_PLAYER)
    return count_owned_item_instances_by_spec(
        inventory,
        runtime._item_repo,
    ).get(_spec_id(runtime), 0)


def _give(runtime: Any) -> None:
    grant_item_specs_to_inventory(
        _PLAYER,
        (_spec_id(runtime),),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _gold(runtime: Any) -> int:
    return runtime._player_status_repo.find_by_id(_PLAYER).gold.value


def _capture_observation_and_trace(
    runtime: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[MarketBoardActivityEvent], list[dict[str, Any]]]:
    events: list[MarketBoardActivityEvent] = []
    recorder = _TraceRecorder()
    runtime._market_service._trace = recorder
    runtime._market_service._now = lambda: 1
    original_publish = runtime._speech_event_publisher.publish_all

    def capture_events(published):
        events.extend(
            event
            for event in published
            if isinstance(event, MarketBoardActivityEvent)
        )
        return original_publish(published)

    monkeypatch.setattr(runtime._speech_event_publisher, "publish_all", capture_events)
    return events, recorder.entries


def _fail_board_save_after_change(monkeypatch: pytest.MonkeyPatch) -> None:
    original_save = InMemoryMarketBoardStore.save

    def fail_after_save(self, board):
        original_save(self, board)
        raise RuntimeError("market board save failed")

    monkeypatch.setattr(InMemoryMarketBoardStore, "save", fail_after_save)


def test_sell_listing_failure_rolls_back_item_board_observation_and_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """売り注文の板保存失敗は預けた品・注文・観測・traceをすべて戻す。"""
    runtime = _runtime()
    _give(runtime)
    events, traces = _capture_observation_and_trace(runtime, monkeypatch)
    before_board = runtime._market_service.board()
    _fail_board_save_after_change(monkeypatch)

    with pytest.raises(RuntimeError, match="market board save failed"):
        runtime._market_service.place_sell_order(
            _PLAYER,
            item_label=_HERB,
            quantity=1,
            unit_price=8,
            current_tick=1,
        )

    assert _held(runtime) == 1
    assert runtime._market_service.board() == before_board
    assert events == []
    assert traces == []


def test_buy_listing_failure_rolls_back_gold_board_observation_and_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """買い注文の板保存失敗は預けたgold・注文・観測・traceをすべて戻す。"""
    runtime = _runtime()
    events, traces = _capture_observation_and_trace(runtime, monkeypatch)
    before_gold = _gold(runtime)
    before_board = runtime._market_service.board()
    _fail_board_save_after_change(monkeypatch)

    with pytest.raises(RuntimeError, match="market board save failed"):
        runtime._market_service.place_buy_order(
            _PLAYER,
            item_label=_HERB,
            quantity=1,
            unit_price=7,
            current_tick=1,
        )

    assert _gold(runtime) == before_gold
    assert runtime._market_service.board() == before_board
    assert events == []
    assert traces == []


def test_buy_reprice_failure_rolls_back_gold_price_observation_and_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """買い注文の値上げ失敗は差額gold・旧価格・観測・traceをすべて戻す。"""
    runtime = _runtime()
    order = runtime._market_service.place_buy_order(
        _PLAYER,
        item_label=_HERB,
        quantity=1,
        unit_price=7,
        current_tick=1,
    )
    events, traces = _capture_observation_and_trace(runtime, monkeypatch)
    before_gold = _gold(runtime)
    _fail_board_save_after_change(monkeypatch)

    with pytest.raises(RuntimeError, match="market board save failed"):
        runtime._market_service.reprice_order(
            _PLAYER,
            item_label=_HERB,
            side=MarketOrderSide.BUY,
            new_unit_price=10,
        )

    assert _gold(runtime) == before_gold
    assert runtime._market_service.board().find(order.order_id).unit_price_gold == 7
    assert events == []
    assert traces == []


def test_sell_cancel_failure_rolls_back_returned_item_order_observation_and_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """売り注文の取り下げ失敗は返却品・注文・観測・traceをすべて戻す。"""
    runtime = _runtime()
    _give(runtime)
    order = runtime._market_service.place_sell_order(
        _PLAYER,
        item_label=_HERB,
        quantity=1,
        unit_price=8,
        current_tick=1,
    )
    events, traces = _capture_observation_and_trace(runtime, monkeypatch)
    _fail_board_save_after_change(monkeypatch)

    with pytest.raises(RuntimeError, match="market board save failed"):
        runtime._market_service.cancel_order(_PLAYER, order_id=order.order_id)

    assert _held(runtime) == 0
    assert runtime._market_service.board().find(order.order_id) == order
    assert events == []
    assert traces == []


def test_buy_listing_cannot_spend_gold_frozen_by_player_trade() -> None:
    """対人取引へ提示中のgoldは市場の買い注文へ二重利用できない。"""
    runtime = create_world_runtime(_TRADE_SCENARIO)
    runtime._player_trade_service.offer(
        PlayerId(1),
        target=PlayerId(2),
        gives_items=(),
        gives_gold=10,
        asks_item_labels=({"item_label": _HERB, "quantity": 1},),
        asks_gold=0,
        current_tick=runtime.current_tick(),
    )
    before_gold = _gold(runtime)
    before_board = runtime._market_service.board()

    with pytest.raises(MarketGoldNotEnoughError) as captured:
        runtime._market_service.place_buy_order(
            PlayerId(1),
            item_label=_HERB,
            quantity=1,
            unit_price=10,
            current_tick=1,
        )

    assert "いま使えるのは2G" in str(captured.value)
    assert _gold(runtime) == before_gold
    assert runtime._market_service.board() == before_board
    assert len(runtime._pending_trade_offer_store.list_all()) == 1
