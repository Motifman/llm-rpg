"""取引系の公開更新入口が確定区間なしで旧repositoryへ戻らない契約。"""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import Mock

import pytest

from ai_rpg_world.application.trade.services.market_service import MarketService
from ai_rpg_world.application.trade.services.player_trade_service import (
    PlayerTradeService,
)
from ai_rpg_world.application.world_graph.spot_graph_merchant_trade_service import (
    SpotGraphMerchantTradeService,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.value_object.market_order_id import MarketOrderId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide


def _untouchable_dependency(name: str) -> Mock:
    dependency = Mock(name=name)
    dependency.configure_mock(
        **{
            method: Mock(side_effect=AssertionError(f"{name}.{method} was touched"))
            for method in (
                "board",
                "find_graph",
                "find_by_id",
                "find_by_name",
                "find_by_spec_id",
                "find_all",
                "list_all",
                "list_for_target",
                "has_offer_between",
                "next_offer_id",
                "put",
                "save",
                "publish_all",
            )
        }
    )
    return dependency


def _player_trade() -> tuple[PlayerTradeService, tuple[Mock, ...]]:
    dependencies = tuple(
        _untouchable_dependency(name)
        for name in (
            "offers",
            "freeze",
            "graph",
            "inventories",
            "statuses",
            "items",
            "item_specs",
            "events",
        )
    )
    service = PlayerTradeService(
        pending_trade_offer_store=dependencies[0],
        trade_freeze_service=dependencies[1],
        spot_graph_repository=dependencies[2],
        player_inventory_repository=dependencies[3],
        player_status_repository=dependencies[4],
        item_repository=dependencies[5],
        item_spec_repository=dependencies[6],
        event_publisher=dependencies[7],
    )
    return service, dependencies


@pytest.mark.parametrize(
    "invoke",
    (
        lambda service: service.offer(
            PlayerId(1),
            target=PlayerId(2),
            gives_items=(),
            gives_gold=0,
            asks_item_labels=(),
            asks_gold=0,
            current_tick=0,
        ),
        lambda service: service.accept(PlayerId(2), offerer=PlayerId(1)),
        lambda service: service.decline(PlayerId(2), offerer=PlayerId(1)),
    ),
)
def test_player_trade_updates_require_command_scope_before_dependencies(
    invoke: Callable[[PlayerTradeService], Any],
) -> None:
    """提案・承諾・辞退はscope未配線なら状態やpublisherへ触れる前に拒否する。"""
    service, dependencies = _player_trade()

    with pytest.raises(RuntimeError, match="CommandScopeFactoryが未配線"):
        invoke(service)

    assert all(dependency.mock_calls == [] for dependency in dependencies)


def _merchant_trade() -> tuple[SpotGraphMerchantTradeService, tuple[Mock, ...]]:
    dependencies = tuple(
        _untouchable_dependency(name)
        for name in (
            "graph",
            "statuses",
            "inventories",
            "items",
            "item_specs",
            "freeze",
            "events",
        )
    )
    service = SpotGraphMerchantTradeService(
        spot_graph_repository=dependencies[0],
        player_status_repository=dependencies[1],
        player_inventory_repository=dependencies[2],
        item_repository=dependencies[3],
        item_spec_repository=dependencies[4],
        trade_freeze_service=dependencies[5],
        event_publisher=dependencies[6],
    )
    return service, dependencies


@pytest.mark.parametrize("method", ("buy", "sell"))
def test_merchant_trade_updates_require_command_scope_before_dependencies(
    method: str,
) -> None:
    """商人との購入・売却はscope未配線なら状態やpublisherへ触れる前に拒否する。"""
    service, dependencies = _merchant_trade()

    with pytest.raises(RuntimeError, match="CommandScopeFactoryが未配線"):
        getattr(service, method)(
            PlayerId(1), merchant_id=1, item_spec_id=1, quantity=1
        )

    assert all(dependency.mock_calls == [] for dependency in dependencies)


def _market() -> tuple[MarketService, tuple[Mock, ...]]:
    dependencies = tuple(
        _untouchable_dependency(name)
        for name in (
            "board",
            "graph",
            "inventories",
            "statuses",
            "items",
            "item_specs",
            "freeze",
            "events",
        )
    )
    service = MarketService(
        market_board_store=dependencies[0],
        spot_graph_repository=dependencies[1],
        player_inventory_repository=dependencies[2],
        player_status_repository=dependencies[3],
        item_repository=dependencies[4],
        item_spec_repository=dependencies[5],
        trade_freeze_service=dependencies[6],
        event_publisher=dependencies[7],
    )
    return service, dependencies


@pytest.mark.parametrize(
    "invoke",
    (
        lambda service: service.place_sell_order(
            PlayerId(1), item_label="薬草", quantity=1, unit_price=1, current_tick=0
        ),
        lambda service: service.place_buy_order(
            PlayerId(1), item_label="薬草", quantity=1, unit_price=1, current_tick=0
        ),
        lambda service: service.take_order(
            PlayerId(1), order_id=MarketOrderId(1), quantity=1, current_tick=0
        ),
        lambda service: service.buy_best(
            PlayerId(1), item_label="薬草", quantity=1, current_tick=0
        ),
        lambda service: service.sell_best(
            PlayerId(1), item_label="薬草", quantity=1, current_tick=0
        ),
        lambda service: service.reprice_order(
            PlayerId(1),
            item_label="薬草",
            side=MarketOrderSide.SELL,
            new_unit_price=2,
        ),
        lambda service: service.cancel_order(
            PlayerId(1), order_id=MarketOrderId(1)
        ),
        lambda service: service.cancel_by(
            PlayerId(1), item_label="薬草", side=MarketOrderSide.SELL
        ),
    ),
)
def test_market_updates_require_command_scope_before_dependencies(
    invoke: Callable[[MarketService], Any],
) -> None:
    """市場の公開更新はscope未配線なら板・資産・publisherへ触れる前に拒否する。"""
    service, dependencies = _market()

    with pytest.raises(RuntimeError, match="CommandScopeFactoryが未配線"):
        invoke(service)

    assert all(dependency.mock_calls == [] for dependency in dependencies)
