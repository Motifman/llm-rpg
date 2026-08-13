from datetime import datetime

import pytest
from unittest.mock import Mock

from ai_rpg_world.application.trade.handlers.trade_event_handler import TradeEventHandler
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeOfferedEvent,
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
)
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.domain.trade.value_object.trade_listing_projection import TradeListingProjection
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import InMemoryTradeReadModelRepository
from ai_rpg_world.infrastructure.events.trade_projection_executor import (
    InMemoryTradeProjectionExecutor,
)

_TS = datetime(2024, 1, 1, 12, 0, 0)


def _listing(seller_name: str = "Seller") -> TradeListingProjection:
    return TradeListingProjection(
        seller_display_name=seller_name,
        item_name="Test Item",
        item_quantity=1,
        item_type=ItemType.CONSUMABLE,
        item_rarity=Rarity.COMMON,
        item_description="Test Desc",
        item_equipment_type=None,
        durability_current=None,
        durability_max=None,
    )


class TestTradeEventHandler:
    @pytest.fixture
    def setup_handler(self):
        read_model_repo = InMemoryTradeReadModelRepository()
        handler = TradeEventHandler(InMemoryTradeProjectionExecutor(read_model_repo))

        return handler, read_model_repo

    def test_handle_trade_offered(self, setup_handler):
        handler, read_model_repo = setup_handler

        seller_id = PlayerId(1)
        item_id = ItemInstanceId(100)

        event = TradeOfferedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            seller_id=seller_id,
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            trade_scope=TradeScope.global_trade(),
            listing_projection=_listing("Seller"),
            trade_created_at=_TS,
        )

        handler.handle_trade_offered(event)

        read_model = read_model_repo.find_by_id(TradeId(1))
        assert read_model is not None
        assert read_model.seller_name == "Seller"
        assert read_model.item_name == "Test Item"
        assert read_model.status == "ACTIVE"

    def test_handle_trade_accepted(self, setup_handler):
        handler, read_model_repo = setup_handler

        assert read_model_repo.find_by_id(TradeId(1)) is not None

        buyer_id = PlayerId(2)

        event = TradeAcceptedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            buyer_id=buyer_id,
            buyer_display_name="Buyer",
            listing_projection=_listing(),
            seller_id=PlayerId(1),
            offered_item_id=ItemInstanceId(100),
            requested_gold=TradeRequestedGold.of(500),
            trade_created_at=_TS,
        )

        handler.handle_trade_accepted(event)

        read_model = read_model_repo.find_by_id(TradeId(1))
        assert read_model.status == "COMPLETED"
        assert read_model.buyer_name == "Buyer"

    def test_handle_trade_accepted_creates_read_model_when_missing(self, setup_handler):
        handler, read_model_repo = setup_handler

        # InMemoryTradeReadModelRepository は 1〜15 のサンプル行を持つため、衝突しない ID を使う
        fresh_trade_id = TradeId(999001)

        event = TradeAcceptedEvent.create(
            aggregate_id=fresh_trade_id,
            aggregate_type="TradeAggregate",
            buyer_id=PlayerId(2),
            buyer_display_name="Buyer",
            listing_projection=_listing(),
            seller_id=PlayerId(1),
            offered_item_id=ItemInstanceId(100),
            requested_gold=TradeRequestedGold.of(300),
            trade_created_at=_TS,
        )

        handler.handle_trade_accepted(event)

        read_model = read_model_repo.find_by_id(fresh_trade_id)
        assert read_model is not None
        assert read_model.status == "COMPLETED"
        assert read_model.buyer_id == 2
        assert read_model.seller_name == _listing().seller_display_name
        assert read_model.requested_gold == 300

    def test_handle_trade_cancelled(self, setup_handler):
        handler, read_model_repo = setup_handler

        assert read_model_repo.find_by_id(TradeId(1)) is not None

        event = TradeCancelledEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
        )

        handler.handle_trade_cancelled(event)

        read_model = read_model_repo.find_by_id(TradeId(1))
        assert read_model.status == "CANCELLED"

    def test_duplicate_event_is_not_projected_twice(self) -> None:
        """同じevent_idを再配送してもread model保存は一度だけ実行する。"""
        repository = InMemoryTradeReadModelRepository()
        original_save = repository.save
        repository.save = Mock(side_effect=original_save)  # type: ignore[method-assign]
        handler = TradeEventHandler(InMemoryTradeProjectionExecutor(repository))
        event = TradeOfferedEvent.create(
            aggregate_id=TradeId(999002),
            aggregate_type="TradeAggregate",
            seller_id=PlayerId(1),
            offered_item_id=ItemInstanceId(100),
            requested_gold=TradeRequestedGold.of(500),
            trade_scope=TradeScope.global_trade(),
            listing_projection=_listing(),
            trade_created_at=_TS,
        )

        handler.handle_trade_offered(event)
        handler.handle_trade_offered(event)

        assert repository.save.call_count == 1  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        ("method_name", "consumer_id"),
        (
            ("handle_trade_offered", TradeEventHandler.OFFERED_CONSUMER_ID),
            ("handle_trade_accepted", TradeEventHandler.ACCEPTED_CONSUMER_ID),
            ("handle_trade_cancelled", TradeEventHandler.CANCELLED_CONSUMER_ID),
            ("handle_trade_declined", TradeEventHandler.DECLINED_CONSUMER_ID),
        ),
    )
    def test_each_handler_uses_stable_consumer_id(
        self,
        method_name: str,
        consumer_id: str,
    ) -> None:
        """4種のhandlerは種類ごとに安定したconsumer IDをexecutorへ渡す。"""
        executor = Mock()
        executor.execute_once.return_value = False
        handler = TradeEventHandler(executor)
        common = {
            "event_id": 123,
            "occurred_at": _TS,
            "aggregate_id": TradeId(999003),
            "aggregate_type": "TradeAggregate",
        }
        events = {
            "handle_trade_offered": TradeOfferedEvent(
                **common,
                seller_id=PlayerId(1),
                offered_item_id=ItemInstanceId(100),
                requested_gold=TradeRequestedGold.of(500),
                trade_scope=TradeScope.global_trade(),
                listing_projection=_listing(),
                trade_created_at=_TS,
            ),
            "handle_trade_accepted": TradeAcceptedEvent(
                **common,
                buyer_id=PlayerId(2),
                buyer_display_name="Buyer",
                listing_projection=_listing(),
                seller_id=PlayerId(1),
                offered_item_id=ItemInstanceId(100),
                requested_gold=TradeRequestedGold.of(500),
                trade_created_at=_TS,
            ),
            "handle_trade_cancelled": TradeCancelledEvent(**common),
            "handle_trade_declined": TradeDeclinedEvent(
                **common,
                decliner_id=PlayerId(2),
            ),
        }

        getattr(handler, method_name)(events[method_name])

        assert executor.execute_once.call_args.kwargs["consumer_id"] == consumer_id
        assert executor.execute_once.call_args.kwargs["event_id"] == 123

    def test_handle_trade_declined(self, setup_handler):
        handler, read_model_repo = setup_handler

        assert read_model_repo.find_by_id(TradeId(1)) is not None

        decliner_id = PlayerId(2)
        event = TradeDeclinedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            decliner_id=decliner_id,
        )

        handler.handle_trade_declined(event)

        read_model = read_model_repo.find_by_id(TradeId(1))
        assert read_model.status == "CANCELLED"
