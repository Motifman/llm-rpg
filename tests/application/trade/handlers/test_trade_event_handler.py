import pytest
from datetime import datetime
from unittest.mock import Mock

from ai_rpg_world.application.trade.handlers.trade_event_handler import TradeEventHandler
from ai_rpg_world.domain.trade.event.trade_event import TradeOfferedEvent, TradeAcceptedEvent, TradeCancelledEvent
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import InMemoryTradeReadModelRepository
from ai_rpg_world.infrastructure.repository.in_memory_trade_repository import InMemoryTradeRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import InMemoryPlayerProfileRepository
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class TestTradeEventHandler:
    @pytest.fixture
    def setup_handler(self):
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        read_model_repo = InMemoryTradeReadModelRepository()
        trade_repo = InMemoryTradeRepository()
        profile_repo = InMemoryPlayerProfileRepository()
        
        # Mock ItemInstanceRepository
        item_instance_repo = Mock()
        
        # Mock UnitOfWorkFactory
        uow_factory = Mock()
        uow_factory.create.side_effect = create_uow

        handler = TradeEventHandler(
            read_model_repo,
            trade_repo,
            profile_repo,
            item_instance_repo,
            uow_factory
        )

        return handler, read_model_repo, trade_repo, profile_repo, item_instance_repo

    def test_handle_trade_offered(self, setup_handler):
        handler, read_model_repo, trade_repo, profile_repo, item_instance_repo = setup_handler
        
        # Setup data
        seller_id = PlayerId(1)
        profile = PlayerProfileAggregate.create(seller_id, PlayerName("Seller"))
        profile_repo.save(profile)
        
        item_id = ItemInstanceId(100)
        mock_item = Mock()
        mock_item.item_spec.name = "Test Item"
        mock_item.item_spec.item_type = ItemType.CONSUMABLE
        mock_item.item_spec.rarity = Rarity.COMMON
        mock_item.item_spec.description = "Test Desc"
        mock_item.quantity = 1
        mock_item.durability = None
        item_instance_repo.find_by_id.return_value = mock_item

        event = TradeOfferedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            seller_id=seller_id,
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            trade_scope=TradeScope.global_trade()
        )

        handler.handle_trade_offered(event)

        # Verify ReadModel
        read_model = read_model_repo.find_by_id(TradeId(1))
        assert read_model is not None
        assert read_model.seller_name == "Seller"
        assert read_model.item_name == "Test Item"
        assert read_model.status == "ACTIVE"

    def test_handle_trade_accepted(self, setup_handler):
        handler, read_model_repo, trade_repo, profile_repo, item_instance_repo = setup_handler
        
        # Setup existing ReadModel
        read_model = Mock(trade_id=1, status="ACTIVE")
        read_model_repo.save(read_model)
        
        buyer_id = PlayerId(2)
        profile = PlayerProfileAggregate.create(buyer_id, PlayerName("Buyer"))
        profile_repo.save(profile)

        event = TradeAcceptedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            buyer_id=buyer_id
        )

        handler.handle_trade_accepted(event)

        # Verify ReadModel update
        read_model = read_model_repo.find_by_id(TradeId(1))
        assert read_model.status == "COMPLETED"
        assert read_model.buyer_name == "Buyer"

    def test_handle_trade_cancelled(self, setup_handler):
        handler, read_model_repo, trade_repo, profile_repo, item_instance_repo = setup_handler
        
        # Setup existing ReadModel
        read_model = Mock(trade_id=1, status="ACTIVE")
        read_model_repo.save(read_model)

        event = TradeCancelledEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate"
        )

        handler.handle_trade_cancelled(event)

        # Verify ReadModel update
        read_model = read_model_repo.find_by_id(TradeId(1))
        assert read_model.status == "CANCELLED"
