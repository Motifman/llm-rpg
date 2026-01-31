import pytest
from datetime import datetime
from unittest.mock import patch

from src.application.trade.services.trade_command_service import TradeCommandService
from src.application.trade.contracts.commands import OfferItemCommand, AcceptTradeCommand, CancelTradeCommand
from src.application.trade.contracts.dtos import TradeCommandResultDto
from src.application.trade.exceptions.command.trade_command_exception import (
    TradeCommandException,
    TradeCreationException,
    TradeNotFoundForCommandException,
    TradeAccessDeniedException
)
from src.domain.player.exception import InsufficientGoldException
from src.domain.player.exception.player_exceptions import ItemNotInSlotException
from src.infrastructure.repository.in_memory_trade_repository import InMemoryTradeRepository
from src.infrastructure.repository.in_memory_player_inventory_repository import InMemoryPlayerInventoryRepository
from src.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from src.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from src.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from src.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from src.domain.player.value_object.player_id import PlayerId
from src.domain.player.value_object.slot_id import SlotId
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.player.value_object.gold import Gold
from src.domain.player.value_object.hp import Hp
from src.domain.player.value_object.mp import Mp
from src.domain.player.value_object.stamina import Stamina
from src.domain.player.value_object.base_stats import BaseStats
from src.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from src.domain.player.value_object.exp_table import ExpTable
from src.domain.player.value_object.growth import Growth
from src.domain.trade.enum.trade_enum import TradeStatus
from src.domain.trade.aggregate.trade_aggregate import TradeAggregate
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.trade.value_object.trade_scope import TradeScope
from src.domain.trade.value_object.trade_requested_gold import TradeRequestedGold


class TestTradeCommandService:
    @pytest.fixture
    def setup_service(self):
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        unit_of_work, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow
        )

        data_store = InMemoryDataStore()
        trade_repository = InMemoryTradeRepository(data_store, unit_of_work)
        inventory_repository = InMemoryPlayerInventoryRepository(data_store, unit_of_work)
        status_repository = InMemoryPlayerStatusRepository(data_store, unit_of_work)

        service = TradeCommandService(
            trade_repository,
            inventory_repository,
            status_repository,
            unit_of_work
        )

        return service, trade_repository, inventory_repository, status_repository, unit_of_work, event_publisher

    def _create_sample_status(self, player_id: int):
        exp_table = ExpTable(100, 1.5)
        return PlayerStatusAggregate(
            player_id=PlayerId(player_id),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100)
        )

    def test_offer_item_success(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _ = setup_service
        
        # Setup seller inventory
        seller_id = 1
        inventory = PlayerInventoryAggregate.create_new_inventory(PlayerId(seller_id))
        item_id = ItemInstanceId(100)
        inventory.acquire_item(item_id)
        inv_repo.save(inventory)

        command = OfferItemCommand(
            seller_id=seller_id,
            item_instance_id=100,
            slot_id=0,
            requested_gold=500
        )

        result = service.offer_item(command)

        assert result.success is True
        trade_id_val = result.data["trade_id"]
        
        # Verify trade aggregate
        trade = trade_repo.find_by_id(TradeId(trade_id_val))
        assert trade is not None
        assert trade.seller_id.value == seller_id
        assert trade.offered_item_id.value == 100
        assert trade.requested_gold.value == 500
        assert trade.status == TradeStatus.ACTIVE

        # Verify item is reserved
        inventory = inv_repo.find_by_id(PlayerId(seller_id))
        assert inventory.is_item_reserved(item_id) is True

    def test_offer_item_seller_inventory_not_found(self, setup_service):
        service, _, _, _, _, _ = setup_service
        
        command = OfferItemCommand(
            seller_id=999,
            item_instance_id=100,
            slot_id=0,
            requested_gold=500
        )

        with pytest.raises(TradeCreationException) as excinfo:
            service.offer_item(command)
        assert "Seller inventory not found" in str(excinfo.value)

    def test_offer_item_slot_mismatch(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _ = setup_service
        
        seller_id = 1
        inventory = PlayerInventoryAggregate.create_new_inventory(PlayerId(seller_id))
        inventory.acquire_item(ItemInstanceId(101)) # Wrong ID
        inv_repo.save(inventory)

        command = OfferItemCommand(
            seller_id=seller_id,
            item_instance_id=100,
            slot_id=0,
            requested_gold=500
        )

        with pytest.raises(TradeCreationException) as excinfo:
            service.offer_item(command)
        assert "Item ID mismatch" in str(excinfo.value)

    def test_offer_item_direct_trade_missing_target(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _ = setup_service
        
        seller_id = 1
        inventory = PlayerInventoryAggregate.create_new_inventory(PlayerId(seller_id))
        inventory.acquire_item(ItemInstanceId(100))
        inv_repo.save(inventory)

        command = OfferItemCommand(
            seller_id=seller_id,
            item_instance_id=100,
            slot_id=0,
            requested_gold=500,
            is_direct=True,
            target_player_id=None # Missing
        )

        with pytest.raises(TradeCreationException) as excinfo:
            service.offer_item(command)
        assert "Target player ID is required" in str(excinfo.value)

    def test_accept_trade_success(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _ = setup_service
        
        # Setup seller and buyer
        seller_id = 1
        buyer_id = 2
        item_id = ItemInstanceId(100)
        
        seller_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(seller_id))
        seller_inv.acquire_item(item_id)
        seller_inv.reserve_item(SlotId(0))
        inv_repo.save(seller_inv)
        
        seller_status = self._create_sample_status(seller_id)
        status_repo.save(seller_status)
        
        buyer_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(buyer_id))
        inv_repo.save(buyer_inv)
        
        buyer_status = self._create_sample_status(buyer_id)
        status_repo.save(buyer_status)
        
        # Setup trade
        trade_id = trade_repo.generate_trade_id()
        trade = TradeAggregate.create_new_trade(
            trade_id=trade_id,
            seller_id=PlayerId(seller_id),
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            created_at=datetime.now(),
            trade_scope=TradeScope.global_trade()
        )
        trade_repo.save(trade)

        command = AcceptTradeCommand(trade_id=trade_id.value, buyer_id=buyer_id)
        result = service.accept_trade(command)

        assert result.success is True
        
        # Verify trade status
        trade = trade_repo.find_by_id(trade_id)
        assert trade.status == TradeStatus.COMPLETED
        assert trade.buyer_id.value == buyer_id

        # Verify gold transfer
        assert status_repo.find_by_id(PlayerId(buyer_id)).gold.value == 500 # 1000 - 500
        assert status_repo.find_by_id(PlayerId(seller_id)).gold.value == 1500 # 1000 + 500

        # Verify item transfer
        assert inv_repo.find_by_id(PlayerId(seller_id)).get_item_instance_id_by_slot(SlotId(0)) is None
        assert inv_repo.find_by_id(PlayerId(buyer_id)).get_item_instance_id_by_slot(SlotId(0)) == item_id

    def test_accept_trade_not_found(self, setup_service):
        service, _, _, _, _, _ = setup_service
        
        command = AcceptTradeCommand(trade_id=999, buyer_id=2)
        with pytest.raises(TradeNotFoundForCommandException):
            service.accept_trade(command)

    def test_accept_trade_self_trade_not_allowed(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _ = setup_service
        
        seller_id = 1
        item_id = ItemInstanceId(100)
        
        seller_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(seller_id))
        seller_inv.acquire_item(item_id)
        seller_inv.reserve_item(SlotId(0))
        inv_repo.save(seller_inv)
        
        trade_id = trade_repo.generate_trade_id()
        trade = TradeAggregate.create_new_trade(
            trade_id=trade_id,
            seller_id=PlayerId(seller_id),
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            created_at=datetime.now(),
            trade_scope=TradeScope.global_trade()
        )
        trade_repo.save(trade)

        # Try to accept own trade
        command = AcceptTradeCommand(trade_id=trade_id.value, buyer_id=seller_id)
        with pytest.raises(TradeAccessDeniedException):
            service.accept_trade(command)

    def test_accept_trade_target_mismatch(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _ = setup_service
        
        seller_id = 1
        buyer_id = 2
        other_id = 3
        item_id = ItemInstanceId(100)
        
        # Setup direct trade for 'other_id'
        trade_id = trade_repo.generate_trade_id()
        trade = TradeAggregate.create_new_trade(
            trade_id=trade_id,
            seller_id=PlayerId(seller_id),
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            created_at=datetime.now(),
            trade_scope=TradeScope.direct_trade(PlayerId(other_id))
        )
        trade_repo.save(trade)

        # 'buyer_id' tries to accept
        command = AcceptTradeCommand(trade_id=trade_id.value, buyer_id=buyer_id)
        with pytest.raises(TradeAccessDeniedException):
            service.accept_trade(command)

    def test_accept_trade_insufficient_gold(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _ = setup_service
        
        seller_id = 1
        buyer_id = 2
        item_id = ItemInstanceId(100)
        
        # Setup seller
        seller_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(seller_id))
        seller_inv.acquire_item(item_id)
        seller_inv.reserve_item(SlotId(0))
        inv_repo.save(seller_inv)
        status_repo.save(self._create_sample_status(seller_id))
        
        # Setup buyer with only 100 gold
        buyer_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(buyer_id))
        inv_repo.save(buyer_inv)
        buyer_status = self._create_sample_status(buyer_id)
        # Manually adjust gold to be insufficient
        buyer_status.pay_gold(900) # Left with 100 gold
        status_repo.save(buyer_status)
        
        # Setup trade for 500 gold
        trade_id = trade_repo.generate_trade_id()
        trade = TradeAggregate.create_new_trade(
            trade_id=trade_id,
            seller_id=PlayerId(seller_id),
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            created_at=datetime.now(),
            trade_scope=TradeScope.global_trade()
        )
        trade_repo.save(trade)

        command = AcceptTradeCommand(trade_id=trade_id.value, buyer_id=buyer_id)
        
        # Should raise TradeCommandException because of InsufficientGoldException (DomainException)
        with pytest.raises(TradeCommandException) as excinfo:
            service.accept_trade(command)
        assert "ゴールドが不足しています" in str(excinfo.value)

    def test_accept_trade_inventory_full(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _ = setup_service
        
        seller_id = 1
        buyer_id = 2
        item_id = ItemInstanceId(100)
        
        # Setup seller
        seller_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(seller_id))
        seller_inv.acquire_item(item_id)
        seller_inv.reserve_item(SlotId(0))
        inv_repo.save(seller_inv)
        status_repo.save(self._create_sample_status(seller_id))
        
        # Setup buyer with full inventory
        buyer_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(buyer_id), max_slots=1)
        buyer_inv.acquire_item(ItemInstanceId(200)) # Fill the only slot
        inv_repo.save(buyer_inv)
        status_repo.save(self._create_sample_status(buyer_id))
        
        # Setup trade
        trade_id = trade_repo.generate_trade_id()
        trade = TradeAggregate.create_new_trade(
            trade_id=trade_id,
            seller_id=PlayerId(seller_id),
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            created_at=datetime.now(),
            trade_scope=TradeScope.global_trade()
        )
        trade_repo.save(trade)

        command = AcceptTradeCommand(trade_id=trade_id.value, buyer_id=buyer_id)
        
        with pytest.raises(TradeCommandException) as excinfo:
            service.accept_trade(command)
        assert "Buyer inventory is full" in str(excinfo.value)

    def test_cancel_trade_success(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _ = setup_service
        
        seller_id = 1
        item_id = ItemInstanceId(100)
        
        seller_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(seller_id))
        seller_inv.acquire_item(item_id)
        seller_inv.reserve_item(SlotId(0))
        inv_repo.save(seller_inv)
        
        trade_id = trade_repo.generate_trade_id()
        trade = TradeAggregate.create_new_trade(
            trade_id=trade_id,
            seller_id=PlayerId(seller_id),
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            created_at=datetime.now(),
            trade_scope=TradeScope.global_trade()
        )
        trade_repo.save(trade)

        command = CancelTradeCommand(trade_id=trade_id.value, player_id=seller_id)
        result = service.cancel_trade(command)

        assert result.success is True
        
        # Verify trade status
        trade = trade_repo.find_by_id(trade_id)
        assert trade.status == TradeStatus.CANCELLED

        # Verify item is unreserved
        inventory = inv_repo.find_by_id(PlayerId(seller_id))
        assert inventory.is_item_reserved(item_id) is False
        assert inventory.get_item_instance_id_by_slot(SlotId(0)) == item_id

    def test_cancel_trade_not_seller(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _ = setup_service
        
        seller_id = 1
        other_id = 2
        item_id = ItemInstanceId(100)
        
        # Setup trade
        trade_id = trade_repo.generate_trade_id()
        trade = TradeAggregate.create_new_trade(
            trade_id=trade_id,
            seller_id=PlayerId(seller_id),
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            created_at=datetime.now(),
            trade_scope=TradeScope.global_trade()
        )
        trade_repo.save(trade)

        command = CancelTradeCommand(trade_id=trade_id.value, player_id=other_id)
        with pytest.raises(TradeAccessDeniedException):
            service.cancel_trade(command)

    def test_cancel_trade_already_completed(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _ = setup_service
        
        seller_id = 1
        buyer_id = 2
        item_id = ItemInstanceId(100)
        
        # Setup seller inventory
        seller_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(seller_id))
        seller_inv.acquire_item(item_id)
        seller_inv.reserve_item(SlotId(0))
        inv_repo.save(seller_inv)
        
        # Setup trade
        trade_id = trade_repo.generate_trade_id()
        trade = TradeAggregate.create_new_trade(
            trade_id=trade_id,
            seller_id=PlayerId(seller_id),
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            created_at=datetime.now(),
            trade_scope=TradeScope.global_trade()
        )
        trade.accept_by(PlayerId(buyer_id)) # Complete it
        trade_repo.save(trade)

        command = CancelTradeCommand(trade_id=trade_id.value, player_id=seller_id)
        
        # Domain will raise InvalidTradeStatusException -> TradeCommandException
        with pytest.raises(TradeCommandException) as excinfo:
            service.cancel_trade(command)
        assert "Trade is already completed or cancelled" in str(excinfo.value)
