import pytest
from datetime import datetime
from unittest.mock import patch

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.trade.services.trade_command_service import TradeCommandService
from ai_rpg_world.application.trade.contracts.commands import (
    OfferItemCommand,
    AcceptTradeCommand,
    CancelTradeCommand,
    DeclineTradeCommand,
)
from ai_rpg_world.application.trade.contracts.dtos import TradeCommandResultDto
from ai_rpg_world.application.trade.exceptions.base_exception import (
    TradeSystemErrorException,
)
from ai_rpg_world.application.trade.exceptions.command.trade_command_exception import (
    TradeCommandException,
    TradeCreationException,
    TradeNotFoundForCommandException,
    TradeAccessDeniedException
)
from ai_rpg_world.domain.player.exception import InsufficientGoldException
from ai_rpg_world.domain.player.exception.player_exceptions import ItemNotInSlotException
from ai_rpg_world.infrastructure.repository.in_memory_trade_repository import InMemoryTradeRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import InMemoryPlayerInventoryRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_trade_command_repository_provider import (
    InMemoryTradeCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionFactory,
)
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.aggregate.trade_aggregate import TradeAggregate
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_listing_projection import TradeListingProjection
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository


def _cmd_trade_listing_projection() -> TradeListingProjection:
    return TradeListingProjection(
        seller_display_name="SellerOne",
        item_name="TradeItem",
        item_quantity=1,
        item_type=ItemType.CONSUMABLE,
        item_rarity=Rarity.COMMON,
        item_description="for trade command tests",
        item_equipment_type=None,
        durability_current=None,
        durability_max=None,
    )


class _NoOpSyncDispatcher:
    def dispatch(self, event: object, context: object) -> None:
        return


class _NoOpAfterCommitHandoff:
    def handoff(self, events: object) -> None:
        return


def _build_in_memory_service(
    *,
    sync_dispatcher: object | None = None,
    after_commit_handoff: object | None = None,
):
    data_store = InMemoryDataStore()
    trade_repository = InMemoryTradeRepository(data_store)
    inventory_repository = InMemoryPlayerInventoryRepository(data_store)
    status_repository = InMemoryPlayerStatusRepository(data_store)
    profile_repository = InMemoryPlayerProfileRepository(data_store)
    item_repository = InMemoryItemRepository(data_store)
    scope_factory = CommandScopeFactory(
        InMemoryUnitOfWorkTransactionFactory(data_store),
        sync_dispatcher=(sync_dispatcher or _NoOpSyncDispatcher()),  # type: ignore[arg-type]
        after_commit_handoff=(
            after_commit_handoff or _NoOpAfterCommitHandoff()
        ),  # type: ignore[arg-type]
        repository_provider_factory=(
            InMemoryTradeCommandRepositoryProviderFactory()
        ),
    )
    service = TradeCommandService(scope_factory)
    return (
        service,
        trade_repository,
        inventory_repository,
        status_repository,
        scope_factory,
        None,
        profile_repository,
        item_repository,
    )


class TestTradeCommandService:
    @pytest.fixture
    def setup_service(self):
        return _build_in_memory_service()

    def _cmd_item_spec(self) -> ItemSpec:
        return ItemSpec(
            item_spec_id=ItemSpecId(1),
            name="TradeItem",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="for trade command tests",
            max_stack_size=MaxStackSize(64),
        )

    def _seed_profile_item(
        self,
        profile_repo: InMemoryPlayerProfileRepository,
        item_repo: InMemoryItemRepository,
        *,
        seller_id: int,
        item_numeric_id: int,
        buyer_ids: list[int],
    ) -> None:
        profile_repo.save(
            PlayerProfileAggregate.create(PlayerId(seller_id), PlayerName("SellerOne"))
        )
        buyer_names = {2: "BuyerOne", 3: "BuyerTwo", 4: "BuyerFou"}
        for bid in buyer_ids:
            nm = buyer_names.get(bid, f"Play{bid}")
            profile_repo.save(PlayerProfileAggregate.create(PlayerId(bid), PlayerName(nm)))
        item_repo.save(
            ItemAggregate.create(
                ItemInstanceId(item_numeric_id), self._cmd_item_spec(), quantity=1
            )
        )

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

    def _seed_active_trade(
        self,
        setup_service,
        *,
        direct_target_id: int | None = None,
    ) -> tuple[TradeId, ItemInstanceId]:
        """予約済み商品を持つ有効な取引と、必要な購入者状態を用意する。"""
        _, trade_repo, inv_repo, status_repo, _, _, profile_repo, item_repo = setup_service
        seller_id = 1
        buyer_id = direct_target_id or 2
        item_id = ItemInstanceId(100)
        self._seed_profile_item(
            profile_repo,
            item_repo,
            seller_id=seller_id,
            item_numeric_id=item_id.value,
            buyer_ids=[buyer_id],
        )
        seller_inventory = PlayerInventoryAggregate.create_new_inventory(PlayerId(seller_id))
        seller_inventory.acquire_item(item_id)
        seller_inventory.reserve_item(SlotId(0))
        inv_repo.save(seller_inventory)
        inv_repo.save(PlayerInventoryAggregate.create_new_inventory(PlayerId(buyer_id)))
        status_repo.save(self._create_sample_status(seller_id))
        status_repo.save(self._create_sample_status(buyer_id))
        trade_id = trade_repo.generate_trade_id()
        trade_repo.save(
            TradeAggregate.create_new_trade(
                trade_id=trade_id,
                seller_id=PlayerId(seller_id),
                offered_item_id=item_id,
                requested_gold=TradeRequestedGold.of(500),
                created_at=datetime.now(),
                trade_scope=(
                    TradeScope.direct_trade(PlayerId(buyer_id))
                    if direct_target_id is not None
                    else TradeScope.global_trade()
                ),
                listing_projection=_cmd_trade_listing_projection(),
            )
        )
        return trade_id, item_id

    def test_offer_item_success(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service
        
        # Setup seller inventory
        seller_id = 1
        self._seed_profile_item(
            profile_repo,
            item_repo,
            seller_id=seller_id,
            item_numeric_id=100,
            buyer_ids=[],
        )
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
        service, _, _, _, _, _, _, _ = setup_service
        
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
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service
        
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
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service
        
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
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service
        
        # Setup seller and buyer
        seller_id = 1
        buyer_id = 2
        item_id = ItemInstanceId(100)
        self._seed_profile_item(
            profile_repo,
            item_repo,
            seller_id=seller_id,
            item_numeric_id=item_id.value,
            buyer_ids=[buyer_id],
        )
        
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
            trade_scope=TradeScope.global_trade(),
            listing_projection=_cmd_trade_listing_projection(),
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

    def test_accept_trade_late_inventory_save_failure_rolls_back_every_change(
        self,
        setup_service,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """購入者inventory保存で失敗すると取引・所持品・双方のgoldをすべて戻す。"""
        service, trade_repo, inv_repo, status_repo, *_ = setup_service
        trade_id, item_id = self._seed_active_trade(setup_service)
        repository_type = type(inv_repo)
        original_save = repository_type.save
        save_count = 0

        def fail_on_buyer_save(repository, inventory):
            nonlocal save_count
            save_count += 1
            result = original_save(repository, inventory)
            if save_count == 2:
                raise RuntimeError("buyer inventory save failed")
            return result

        monkeypatch.setattr(repository_type, "save", fail_on_buyer_save)

        with pytest.raises(TradeSystemErrorException, match="buyer inventory save failed"):
            service.accept_trade(AcceptTradeCommand(trade_id=trade_id.value, buyer_id=2))

        trade = trade_repo.find_by_id(trade_id)
        assert trade is not None
        assert trade.status is TradeStatus.ACTIVE
        assert trade.buyer_id is None
        seller_inventory = inv_repo.find_by_id(PlayerId(1))
        buyer_inventory = inv_repo.find_by_id(PlayerId(2))
        assert seller_inventory is not None
        assert buyer_inventory is not None
        assert seller_inventory.is_item_reserved(item_id) is True
        assert seller_inventory.get_item_instance_id_by_slot(SlotId(0)) == item_id
        assert buyer_inventory.get_item_instance_id_by_slot(SlotId(0)) is None
        assert status_repo.find_by_id(PlayerId(1)).gold.value == 1000
        assert status_repo.find_by_id(PlayerId(2)).gold.value == 1000

    def test_accept_trade_not_found(self, setup_service):
        service, _, _, _, _, _, _, _ = setup_service
        
        command = AcceptTradeCommand(trade_id=999, buyer_id=2)
        with pytest.raises(TradeNotFoundForCommandException):
            service.accept_trade(command)

    def test_accept_trade_self_trade_not_allowed(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service
        
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
            trade_scope=TradeScope.global_trade(),
            listing_projection=_cmd_trade_listing_projection(),
        )
        trade_repo.save(trade)

        # Try to accept own trade
        command = AcceptTradeCommand(trade_id=trade_id.value, buyer_id=seller_id)
        with pytest.raises(TradeAccessDeniedException):
            service.accept_trade(command)

    def test_accept_trade_target_mismatch(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service
        
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
            trade_scope=TradeScope.direct_trade(PlayerId(other_id)),
            listing_projection=_cmd_trade_listing_projection(),
        )
        trade_repo.save(trade)

        # 'buyer_id' tries to accept
        command = AcceptTradeCommand(trade_id=trade_id.value, buyer_id=buyer_id)
        with pytest.raises(TradeAccessDeniedException):
            service.accept_trade(command)

    def test_accept_trade_insufficient_gold(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service
        
        seller_id = 1
        buyer_id = 2
        item_id = ItemInstanceId(100)
        self._seed_profile_item(
            profile_repo,
            item_repo,
            seller_id=seller_id,
            item_numeric_id=item_id.value,
            buyer_ids=[buyer_id],
        )
        
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
            trade_scope=TradeScope.global_trade(),
            listing_projection=_cmd_trade_listing_projection(),
        )
        trade_repo.save(trade)

        command = AcceptTradeCommand(trade_id=trade_id.value, buyer_id=buyer_id)
        
        # Should raise TradeCommandException because of InsufficientGoldException (DomainException)
        with pytest.raises(TradeCommandException) as excinfo:
            service.accept_trade(command)
        assert "ゴールドが不足しています" in str(excinfo.value)

    def test_accept_trade_inventory_full(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service
        
        seller_id = 1
        buyer_id = 2
        item_id = ItemInstanceId(100)
        self._seed_profile_item(
            profile_repo,
            item_repo,
            seller_id=seller_id,
            item_numeric_id=item_id.value,
            buyer_ids=[buyer_id],
        )
        
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
            trade_scope=TradeScope.global_trade(),
            listing_projection=_cmd_trade_listing_projection(),
        )
        trade_repo.save(trade)

        command = AcceptTradeCommand(trade_id=trade_id.value, buyer_id=buyer_id)
        
        with pytest.raises(TradeCommandException) as excinfo:
            service.accept_trade(command)
        assert "Buyer inventory is full" in str(excinfo.value)

    def test_cancel_trade_success(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service
        
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
            trade_scope=TradeScope.global_trade(),
            listing_projection=_cmd_trade_listing_projection(),
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

    def test_cancel_trade_inventory_save_failure_rolls_back_trade_and_reservation(
        self,
        setup_service,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """予約解除の保存失敗時は先に保存した取引取消も含めて元へ戻す。"""
        service, trade_repo, inv_repo, *_ = setup_service
        trade_id, item_id = self._seed_active_trade(setup_service)
        repository_type = type(inv_repo)
        original_save = repository_type.save

        def fail_after_save(repository, inventory):
            original_save(repository, inventory)
            raise RuntimeError("cancel inventory save failed")

        monkeypatch.setattr(repository_type, "save", fail_after_save)

        with pytest.raises(TradeSystemErrorException, match="cancel inventory save failed"):
            service.cancel_trade(CancelTradeCommand(trade_id=trade_id.value, player_id=1))

        trade = trade_repo.find_by_id(trade_id)
        inventory = inv_repo.find_by_id(PlayerId(1))
        assert trade is not None
        assert inventory is not None
        assert trade.status is TradeStatus.ACTIVE
        assert inventory.is_item_reserved(item_id) is True

    def test_cancel_trade_not_seller(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service
        
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
            trade_scope=TradeScope.global_trade(),
            listing_projection=_cmd_trade_listing_projection(),
        )
        trade_repo.save(trade)

        command = CancelTradeCommand(trade_id=trade_id.value, player_id=other_id)
        with pytest.raises(TradeAccessDeniedException):
            service.cancel_trade(command)

    def test_cancel_trade_already_completed(self, setup_service):
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service
        
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
            trade_scope=TradeScope.global_trade(),
            listing_projection=_cmd_trade_listing_projection(),
        )
        trade.accept_by(
            PlayerId(buyer_id),
            "BuyerOne",
            _cmd_trade_listing_projection(),
        )
        trade_repo.save(trade)

        command = CancelTradeCommand(trade_id=trade_id.value, player_id=seller_id)
        
        # Domain will raise InvalidTradeStatusException -> TradeCommandException
        with pytest.raises(TradeCommandException) as excinfo:
            service.cancel_trade(command)
        assert "Trade is already completed or cancelled" in str(excinfo.value)

    def test_decline_trade_success(self, setup_service):
        """直接取引の宛先が断ると成功する"""
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service

        seller_id = 1
        target_id = 2
        item_id = ItemInstanceId(100)

        # 出品者インベントリ（アイテム予約済み）
        seller_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(seller_id))
        seller_inv.acquire_item(item_id)
        seller_inv.reserve_item(SlotId(0))
        inv_repo.save(seller_inv)

        # 直接取引（target_id 宛て）
        trade_id = trade_repo.generate_trade_id()
        trade = TradeAggregate.create_new_trade(
            trade_id=trade_id,
            seller_id=PlayerId(seller_id),
            offered_item_id=item_id,
            requested_gold=TradeRequestedGold.of(500),
            created_at=datetime.now(),
            trade_scope=TradeScope.direct_trade(PlayerId(target_id)),
            listing_projection=_cmd_trade_listing_projection(),
        )
        trade_repo.save(trade)

        command = DeclineTradeCommand(trade_id=trade_id.value, decliner_id=target_id)
        result = service.decline_trade(command)

        assert result.success is True

        trade = trade_repo.find_by_id(trade_id)
        assert trade.status == TradeStatus.CANCELLED

        # アイテムの予約解除を確認
        inventory = inv_repo.find_by_id(PlayerId(seller_id))
        assert inventory.is_item_reserved(item_id) is False
        assert inventory.get_item_instance_id_by_slot(SlotId(0)) == item_id

    def test_decline_trade_inventory_save_failure_rolls_back_trade_and_reservation(
        self,
        setup_service,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """直接取引を断る途中で保存に失敗すると取消と予約解除をともに戻す。"""
        service, trade_repo, inv_repo, *_ = setup_service
        trade_id, item_id = self._seed_active_trade(
            setup_service,
            direct_target_id=2,
        )
        repository_type = type(inv_repo)
        original_save = repository_type.save

        def fail_after_save(repository, inventory):
            original_save(repository, inventory)
            raise RuntimeError("decline inventory save failed")

        monkeypatch.setattr(repository_type, "save", fail_after_save)

        with pytest.raises(TradeSystemErrorException, match="decline inventory save failed"):
            service.decline_trade(DeclineTradeCommand(trade_id=trade_id.value, decliner_id=2))

        trade = trade_repo.find_by_id(trade_id)
        inventory = inv_repo.find_by_id(PlayerId(1))
        assert trade is not None
        assert inventory is not None
        assert trade.status is TradeStatus.ACTIVE
        assert inventory.is_item_reserved(item_id) is True

    def test_decline_trade_not_found(self, setup_service):
        """存在しない取引を断ろうとするとTradeNotFoundForCommandException"""
        service, _, _, _, _, _, _, _ = setup_service
        command = DeclineTradeCommand(trade_id=999, decliner_id=2)
        with pytest.raises(TradeNotFoundForCommandException):
            service.decline_trade(command)

    def test_decline_trade_seller_cannot_decline(self, setup_service):
        """出品者は自分の取引を断れない"""
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service

        seller_id = 1
        target_id = 2
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
            trade_scope=TradeScope.direct_trade(PlayerId(target_id)),
            listing_projection=_cmd_trade_listing_projection(),
        )
        trade_repo.save(trade)

        command = DeclineTradeCommand(trade_id=trade_id.value, decliner_id=seller_id)
        with pytest.raises(TradeCommandException) as excinfo:
            service.decline_trade(command)
        assert "Cannot decline" in str(excinfo.value) or "断れ" in str(excinfo.value)

    def test_decline_trade_non_target_cannot_decline(self, setup_service):
        """直接取引の宛先以外は断れない"""
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service

        seller_id = 1
        target_id = 2
        other_id = 3
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
            trade_scope=TradeScope.direct_trade(PlayerId(target_id)),
            listing_projection=_cmd_trade_listing_projection(),
        )
        trade_repo.save(trade)

        command = DeclineTradeCommand(trade_id=trade_id.value, decliner_id=other_id)
        with pytest.raises(TradeCommandException) as excinfo:
            service.decline_trade(command)
        assert "Cannot decline" in str(excinfo.value) or "Only" in str(excinfo.value)

    def test_decline_trade_global_raises(self, setup_service):
        """グローバル取引は断れない"""
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service

        seller_id = 1
        buyer_id = 2
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
            trade_scope=TradeScope.global_trade(),
            listing_projection=_cmd_trade_listing_projection(),
        )
        trade_repo.save(trade)

        command = DeclineTradeCommand(trade_id=trade_id.value, decliner_id=buyer_id)
        with pytest.raises(TradeCommandException) as excinfo:
            service.decline_trade(command)
        assert "Only direct" in str(excinfo.value) or "direct" in str(excinfo.value).lower()

    def test_decline_trade_already_cancelled(self, setup_service):
        """キャンセル済み取引を断ろうとするとTradeCommandExceptionが発生する"""
        service, trade_repo, inv_repo, status_repo, uow, _, profile_repo, item_repo = setup_service

        seller_id = 1
        target_id = 2
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
            trade_scope=TradeScope.direct_trade(PlayerId(target_id)),
            listing_projection=_cmd_trade_listing_projection(),
        )
        trade.cancel_by(PlayerId(seller_id))  # 出品者がキャンセル済み
        trade_repo.save(trade)

        command = DeclineTradeCommand(trade_id=trade_id.value, decliner_id=target_id)
        with pytest.raises(TradeCommandException) as excinfo:
            service.decline_trade(command)
        assert "already completed or cancelled" in str(excinfo.value)
