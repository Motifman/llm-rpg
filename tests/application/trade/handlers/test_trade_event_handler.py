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
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork

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
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        read_model_repo = InMemoryTradeReadModelRepository()
        uow_factory = Mock()
        uow_factory.create.side_effect = create_uow

        handler = TradeEventHandler(read_model_repo, uow_factory)

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

        read_model = Mock(trade_id=1, status="ACTIVE")
        read_model_repo.save(read_model)

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

        read_model = Mock(trade_id=1, status="ACTIVE")
        read_model_repo.save(read_model)

        event = TradeCancelledEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
        )

        handler.handle_trade_cancelled(event)

        read_model = read_model_repo.find_by_id(TradeId(1))
        assert read_model.status == "CANCELLED"

    def test_handle_trade_declined(self, setup_handler):
        handler, read_model_repo = setup_handler

        read_model = Mock(trade_id=1, status="ACTIVE")
        read_model_repo.save(read_model)

        decliner_id = PlayerId(2)
        event = TradeDeclinedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            decliner_id=decliner_id,
        )

        handler.handle_trade_declined(event)

        read_model = read_model_repo.find_by_id(TradeId(1))
        assert read_model.status == "CANCELLED"
