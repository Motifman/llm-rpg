"""UseItemApplicationService の正常・例外ケースの網羅的テスト"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.world.services.use_item_service import UseItemApplicationService
from ai_rpg_world.application.world.services.player_use_item_service import PlayerUseItemApplicationService
from ai_rpg_world.application.world.contracts.commands import UseItemCommand
from ai_rpg_world.application.world.exceptions.command.use_command_exception import (
    NoItemInSlotForUseException,
    ItemNotConsumableException,
    ItemReservedForUseException,
    PlayerDownedCannotUseItemException,
    UseItemPlayerNotFoundException,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
from ai_rpg_world.domain.item.value_object.item_effect import HealEffect
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
    InMemoryItemSpecRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent


def _make_uow_and_publisher(data_store):
    """イベント処理エラーを避けるため、ダミーのevent_publisher付きUoWを作成"""
    def create_uow():
        return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)
    return InMemoryUnitOfWork.create_with_event_publisher(
        unit_of_work_factory=create_uow, data_store=data_store
    )


def _consumable_heal_spec(item_spec_id: int = 900) -> ItemSpec:
    return ItemSpec(
        item_spec_id=ItemSpecId(item_spec_id),
        name="回復ポーション",
        item_type=ItemType.CONSUMABLE,
        rarity=Rarity.COMMON,
        description="HPを50回復する",
        max_stack_size=MaxStackSize(10),
        consume_effect=HealEffect(amount=50),
    )


def _non_consumable_spec(item_spec_id: int = 901) -> ItemSpec:
    return ItemSpec(
        item_spec_id=ItemSpecId(item_spec_id),
        name="鉄鉱石",
        item_type=ItemType.MATERIAL,
        rarity=Rarity.COMMON,
        description="基本的な素材",
        max_stack_size=MaxStackSize(64),
    )


class TestUseItemApplicationService:
    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def unit_of_work(self, data_store):
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)
        return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

    @pytest.fixture
    def repos(self, data_store, unit_of_work):
        inv_repo = InMemoryPlayerInventoryRepository(data_store, unit_of_work)
        status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        item_repo = InMemoryItemRepository(data_store, unit_of_work)
        spec_repo = InMemoryItemSpecRepository()
        return inv_repo, status_repo, item_repo, spec_repo

    @pytest.fixture
    def service(self, repos, unit_of_work):
        inv_repo, status_repo, item_repo, spec_repo = repos
        return UseItemApplicationService(
            player_inventory_repository=inv_repo,
            player_status_repository=status_repo,
            item_repository=item_repo,
            unit_of_work=unit_of_work,
            event_publisher=None,
        )

    @pytest.fixture
    def player_with_consumable(self, repos):
        inv_repo, status_repo, item_repo, spec_repo = repos
        player_id_val = 1
        spec = _consumable_heal_spec(900)
        spec_rm = ItemSpecReadModel.create_from_item_spec(
            item_spec_id=spec.item_spec_id,
            name=spec.name,
            item_type=spec.item_type,
            rarity=spec.rarity,
            description=spec.description,
            max_stack_size=spec.max_stack_size,
            consume_effect=spec.consume_effect,
        )
        spec_repo.save(spec_rm)
        item_instance_id = item_repo.generate_item_instance_id()
        item_agg = ItemAggregate.create(item_instance_id, spec, durability=None, quantity=1)
        item_repo.save(item_agg)
        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(player_id_val))
        inv.acquire_item(item_instance_id)
        inv_repo.save(inv)
        exp_table = ExpTable(100, 1.5)
        nav = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )
        status = PlayerStatusAggregate(
            player_id=PlayerId(player_id_val),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100),
            navigation_state=nav,
        )
        status_repo.save(status)
        return player_id_val

    def test_use_item_success(self, service, repos, player_with_consumable):
        """正常: 消費可能アイテムを使用するとインベントリから減り、アイテムが削除される"""
        inv_repo, status_repo, item_repo, spec_repo = repos
        player_id_val = player_with_consumable
        inv_before = inv_repo.find_by_id(PlayerId(player_id_val))
        item_id_before = inv_before.get_item_instance_id_by_slot(SlotId(0))
        assert item_id_before is not None
        service.use_item(UseItemCommand(player_id=player_id_val, inventory_slot_id=0))
        assert item_repo.find_by_id(item_id_before) is None
        inv_after = inv_repo.find_by_id(PlayerId(player_id_val))
        assert inv_after.get_item_instance_id_by_slot(SlotId(0)) is None

    def test_use_item_no_item_in_slot_raises(self, service, repos, player_with_consumable):
        """スロットにアイテムがない場合は NoItemInSlotForUseException"""
        inv_repo, status_repo, item_repo, spec_repo = repos
        player_id_val = player_with_consumable
        inv = inv_repo.find_by_id(PlayerId(player_id_val))
        inv.remove_item_for_placement(SlotId(0))
        inv_repo.save(inv)
        with pytest.raises(NoItemInSlotForUseException):
            service.use_item(UseItemCommand(player_id=player_id_val, inventory_slot_id=0))

    def test_use_item_not_consumable_raises(self, service, repos):
        """消費可能でないアイテムの場合は ItemNotConsumableException"""
        inv_repo, status_repo, item_repo, spec_repo = repos
        player_id_val = 1
        spec = _non_consumable_spec(901)
        spec_rm = ItemSpecReadModel.create_from_item_spec(
            item_spec_id=spec.item_spec_id,
            name=spec.name,
            item_type=spec.item_type,
            rarity=spec.rarity,
            description=spec.description,
            max_stack_size=spec.max_stack_size,
        )
        spec_repo.save(spec_rm)
        item_instance_id = item_repo.generate_item_instance_id()
        item_agg = ItemAggregate.create(item_instance_id, spec, durability=None, quantity=1)
        item_repo.save(item_agg)
        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(player_id_val))
        inv.acquire_item(item_instance_id)
        inv_repo.save(inv)
        exp_table = ExpTable(100, 1.5)
        nav = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )
        status = PlayerStatusAggregate(
            player_id=PlayerId(player_id_val),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100),
            navigation_state=nav,
        )
        status_repo.save(status)
        with pytest.raises(ItemNotConsumableException):
            service.use_item(UseItemCommand(player_id=player_id_val, inventory_slot_id=0))

    def test_use_item_player_not_found_raises(self, service, repos):
        """プレイヤーステータスが見つからない場合は UseItemPlayerNotFoundException"""
        with pytest.raises(UseItemPlayerNotFoundException):
            service.use_item(UseItemCommand(player_id=999, inventory_slot_id=0))

    def test_use_item_empty_inventory_raises(self, service, repos):
        """インベントリが空のスロットを指定すると NoItemInSlotForUseException"""
        inv_repo, status_repo, item_repo, spec_repo = repos
        player_id_val = 1
        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(player_id_val))
        inv_repo.save(inv)
        exp_table = ExpTable(100, 1.5)
        nav = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )
        status = PlayerStatusAggregate(
            player_id=PlayerId(player_id_val),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100),
            navigation_state=nav,
        )
        status_repo.save(status)
        with pytest.raises(NoItemInSlotForUseException):
            service.use_item(UseItemCommand(player_id=player_id_val, inventory_slot_id=0))

    def test_use_item_reserved_item_raises(self, service, repos, player_with_consumable):
        """予約中アイテムの場合は ItemReservedForUseException"""
        inv_repo, status_repo, item_repo, spec_repo = repos
        player_id_val = player_with_consumable
        inv = inv_repo.find_by_id(PlayerId(player_id_val))
        inv.reserve_item(SlotId(0))
        inv_repo.save(inv)
        with pytest.raises(ItemReservedForUseException):
            service.use_item(UseItemCommand(player_id=player_id_val, inventory_slot_id=0))

    def test_use_item_downed_player_raises(self, service, repos, player_with_consumable):
        """ダウン状態のプレイヤーは PlayerDownedCannotUseItemException"""
        inv_repo, status_repo, item_repo, spec_repo = repos
        player_id_val = player_with_consumable
        status = status_repo.find_by_id(PlayerId(player_id_val))
        status.apply_damage(1000)
        status_repo.save(status)
        with pytest.raises(PlayerDownedCannotUseItemException):
            service.use_item(UseItemCommand(player_id=player_id_val, inventory_slot_id=0))

    def test_use_item_command_validation_player_id_zero_raises(self, service):
        """player_id <= 0 の場合 UseItemCommand が ValueError"""
        with pytest.raises(ValueError, match="player_id"):
            UseItemCommand(player_id=0, inventory_slot_id=0)

    def test_use_item_command_validation_slot_negative_raises(self, service):
        """inventory_slot_id < 0 の場合 UseItemCommand が ValueError"""
        with pytest.raises(ValueError, match="inventory_slot_id"):
            UseItemCommand(player_id=1, inventory_slot_id=-1)

    def test_use_item_reserved_raises(self, service, repos, player_with_consumable):
        """予約中アイテムの場合は ItemReservedForUseException"""
        inv_repo, status_repo, item_repo, spec_repo = repos
        player_id_val = player_with_consumable
        inv = inv_repo.find_by_id(PlayerId(player_id_val))
        inv.reserve_item(SlotId(0))
        inv_repo.save(inv)
        with pytest.raises(ItemReservedForUseException):
            service.use_item(UseItemCommand(player_id=player_id_val, inventory_slot_id=0))


class TestPlayerUseItemApplicationService:
    """PlayerUseItemApplicationService のテスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def unit_of_work(self, data_store):
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)
        return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

    @pytest.fixture
    def repos(self, data_store, unit_of_work):
        inv_repo = InMemoryPlayerInventoryRepository(data_store, unit_of_work)
        status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        item_repo = InMemoryItemRepository(data_store, unit_of_work)
        spec_repo = InMemoryItemSpecRepository()
        return inv_repo, status_repo, item_repo, spec_repo

    @pytest.fixture
    def use_item_service(self, repos, unit_of_work):
        inv_repo, status_repo, item_repo, spec_repo = repos
        return UseItemApplicationService(
            player_inventory_repository=inv_repo,
            player_status_repository=status_repo,
            item_repository=item_repo,
            unit_of_work=unit_of_work,
            event_publisher=None,
        )

    @pytest.fixture
    def facade(self, use_item_service, repos):
        _, status_repo, _, _ = repos
        from ai_rpg_world.application.world.services.player_use_item_service import (
            PlayerUseItemApplicationService,
        )
        return PlayerUseItemApplicationService(
            use_item_service=use_item_service,
            player_status_repository=status_repo,
        )

    @pytest.fixture
    def player_with_consumable(self, repos):
        inv_repo, status_repo, item_repo, spec_repo = repos
        player_id_val = 1
        spec = _consumable_heal_spec(900)
        spec_rm = ItemSpecReadModel.create_from_item_spec(
            item_spec_id=spec.item_spec_id,
            name=spec.name,
            item_type=spec.item_type,
            rarity=spec.rarity,
            description=spec.description,
            max_stack_size=spec.max_stack_size,
            consume_effect=spec.consume_effect,
        )
        spec_repo.save(spec_rm)
        item_instance_id = item_repo.generate_item_instance_id()
        item_agg = ItemAggregate.create(item_instance_id, spec, durability=None, quantity=1)
        item_repo.save(item_agg)
        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(player_id_val))
        inv.acquire_item(item_instance_id)
        inv_repo.save(inv)
        exp_table = ExpTable(100, 1.5)
        nav = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )
        status = PlayerStatusAggregate(
            player_id=PlayerId(player_id_val),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100),
            navigation_state=nav,
        )
        status_repo.save(status)
        return player_id_val

    def test_use_item_success(self, facade, repos, player_with_consumable):
        """正常: use_item で消費可能アイテムを使用できる"""
        inv_repo, _, item_repo, _ = repos
        player_id_val = player_with_consumable
        inv_before = inv_repo.find_by_id(PlayerId(player_id_val))
        item_id_before = inv_before.get_item_instance_id_by_slot(SlotId(0))
        assert item_id_before is not None
        facade.use_item(player_id=player_id_val, inventory_slot_id=0)
        assert item_repo.find_by_id(item_id_before) is None
        inv_after = inv_repo.find_by_id(PlayerId(player_id_val))
        assert inv_after.get_item_instance_id_by_slot(SlotId(0)) is None

    def test_use_item_player_not_found_raises(self, facade):
        """プレイヤーステータスが見つからない場合は UseItemPlayerNotFoundException"""
        with pytest.raises(UseItemPlayerNotFoundException):
            facade.use_item(player_id=999, inventory_slot_id=0)
