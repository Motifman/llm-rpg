"""DropItemApplicationService の正常・例外ケースの網羅的テスト"""

import pytest
from ai_rpg_world.application.world.services.drop_item_service import DropItemApplicationService
from ai_rpg_world.application.world.contracts.commands import DropItemCommand
from ai_rpg_world.application.world.exceptions.command.drop_command_exception import (
    NoItemInSlotForDropException,
    ItemReservedForDropException,
    DropPlayerOrInventoryNotFoundException,
)
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
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
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


def _potion_spec() -> ItemSpec:
    return ItemSpec(
        item_spec_id=ItemSpecId(100),
        name="Potion",
        item_type=ItemType.CONSUMABLE,
        rarity=Rarity.COMMON,
        description="Heals",
        max_stack_size=MaxStackSize(10),
        is_placeable=False,
        placeable_object_type=None,
    )


class TestDropItemApplicationService:
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
        return inv_repo, status_repo, item_repo

    @pytest.fixture
    def service(self, repos, unit_of_work):
        inv_repo, status_repo, _ = repos
        return DropItemApplicationService(
            player_inventory_repository=inv_repo,
            player_status_repository=status_repo,
            unit_of_work=unit_of_work,
        )

    @pytest.fixture
    def player_with_item(self, repos):
        inv_repo, status_repo, item_repo = repos
        player_id_val = 1
        spec = _potion_spec()
        item_instance_id = item_repo.generate_item_instance_id()
        item_agg = ItemAggregate.create(item_instance_id, spec, durability=None, quantity=1)
        item_repo.save(item_agg)
        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(player_id_val))
        inv.acquire_item(item_instance_id)
        inv_repo.save(inv)
        exp_table = ExpTable(100, 1.5)
        nav = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(2, 2, 0),
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
        return inv_repo, status_repo, player_id_val

    def test_drop_item_success_empties_slot(self, service, repos, player_with_item):
        """ドロップ成功: 指定スロットが空になること"""
        inv_repo, _, player_id_val = player_with_item
        service.drop_item(DropItemCommand(player_id=player_id_val, inventory_slot_id=0))
        inv = inv_repo.find_by_id(PlayerId(player_id_val))
        assert inv.get_item_instance_id_by_slot(SlotId(0)) is None

    def test_drop_item_no_item_in_slot_raises(self, service, repos, player_with_item):
        """空スロットの場合は NoItemInSlotForDropException"""
        inv_repo, status_repo, player_id_val = player_with_item
        inv = inv_repo.find_by_id(PlayerId(player_id_val))
        inv.drop_item(SlotId(0))
        inv_repo.save(inv)

        with pytest.raises(NoItemInSlotForDropException):
            service.drop_item(DropItemCommand(player_id=player_id_val, inventory_slot_id=0))

    def test_drop_item_reserved_item_raises(self, service, repos, player_with_item):
        """予約中アイテムの場合は ItemReservedForDropException"""
        inv_repo, status_repo, player_id_val = player_with_item
        inv = inv_repo.find_by_id(PlayerId(player_id_val))
        inv.reserve_item(SlotId(0))
        inv_repo.save(inv)

        with pytest.raises(ItemReservedForDropException):
            service.drop_item(DropItemCommand(player_id=player_id_val, inventory_slot_id=0))

    def test_drop_item_no_player_position_raises(self, service, repos, player_with_item):
        """プレイヤー位置がない場合は DropPlayerOrInventoryNotFoundException"""
        inv_repo, status_repo, player_id_val = player_with_item
        exp_table = ExpTable(100, 1.5)
        status_no_pos = PlayerStatusAggregate(
            player_id=PlayerId(player_id_val),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100),
            navigation_state=PlayerNavigationState.empty(),
        )
        status_repo.save(status_no_pos)

        with pytest.raises(DropPlayerOrInventoryNotFoundException):
            service.drop_item(DropItemCommand(player_id=player_id_val, inventory_slot_id=0))

    def test_drop_item_player_not_found_raises(self, service, repos):
        """存在しないプレイヤー（status なし）の場合は DropPlayerOrInventoryNotFoundException"""
        inv_repo, status_repo, _ = repos

        with pytest.raises(DropPlayerOrInventoryNotFoundException):
            service.drop_item(DropItemCommand(player_id=999, inventory_slot_id=0))


class TestPlayerDropItemApplicationService:
    """PlayerDropItemApplicationService の正常・例外テスト"""

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
        return inv_repo, status_repo, item_repo

    @pytest.fixture
    def drop_item_service(self, repos, unit_of_work):
        inv_repo, status_repo, _ = repos
        return DropItemApplicationService(
            player_inventory_repository=inv_repo,
            player_status_repository=status_repo,
            unit_of_work=unit_of_work,
        )

    @pytest.fixture
    def facade(self, drop_item_service, repos):
        _, status_repo, _ = repos
        from ai_rpg_world.application.world.services.player_drop_item_service import (
            PlayerDropItemApplicationService,
        )
        return PlayerDropItemApplicationService(
            drop_item_service=drop_item_service,
            player_status_repository=status_repo,
        )

    @pytest.fixture
    def player_with_item(self, repos):
        inv_repo, status_repo, item_repo = repos
        player_id_val = 1
        spec = _potion_spec()
        item_instance_id = item_repo.generate_item_instance_id()
        item_agg = ItemAggregate.create(item_instance_id, spec, durability=None, quantity=1)
        item_repo.save(item_agg)
        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(player_id_val))
        inv.acquire_item(item_instance_id)
        inv_repo.save(inv)
        exp_table = ExpTable(100, 1.5)
        nav = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(2, 2, 0),
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
        return inv_repo, player_id_val

    def test_drop_from_slot_success(self, facade, player_with_item):
        """drop_from_slot 成功時はインベントリからアイテムが消える"""
        inv_repo, player_id_val = player_with_item
        facade.drop_from_slot(player_id=player_id_val, inventory_slot_id=0)
        inv = inv_repo.find_by_id(PlayerId(player_id_val))
        assert inv.get_item_instance_id_by_slot(SlotId(0)) is None

    def test_drop_from_slot_no_status_raises(self, facade, repos):
        """プレイヤー status がない場合は DropPlayerOrInventoryNotFoundException"""
        with pytest.raises(DropPlayerOrInventoryNotFoundException):
            facade.drop_from_slot(player_id=999, inventory_slot_id=0)
