"""PlaceObjectApplicationService の正常・例外ケースの網羅的テスト"""

import pytest
from ai_rpg_world.application.world.services.place_object_service import PlaceObjectApplicationService
from ai_rpg_world.application.world.contracts.commands import PlaceObjectCommand, DestroyPlaceableCommand
from ai_rpg_world.application.world.exceptions.command.place_command_exception import (
    PlaceCommandException,
    ItemNotPlaceableException,
    NoItemInSlotException,
    PlacementSpotNotFoundException,
    PlacementBlockedException,
    NoPlaceableInFrontException,
)
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    ChestComponent,
    PlaceableComponent,
    StaticPlaceableInnerComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
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
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import InMemoryPlayerInventoryRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import InMemoryItemSpecRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


def _create_map(spot_id_int: int = 1, size: int = 5) -> PhysicalMapAggregate:
    tiles = [
        Tile(Coordinate(x, y, 0), TerrainType.road())
        for x in range(size)
        for y in range(size)
    ]
    return PhysicalMapAggregate.create(SpotId(spot_id_int), tiles)


def _placeable_chest_spec() -> ItemSpec:
    return ItemSpec(
        item_spec_id=ItemSpecId(900),
        name="Placeable Chest",
        item_type=ItemType.OTHER,
        rarity=Rarity.COMMON,
        description="A chest you can place",
        max_stack_size=MaxStackSize(1),
        is_placeable=True,
        placeable_object_type="CHEST",
    )


class TestPlaceObjectApplicationService:
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
        map_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
        inv_repo = InMemoryPlayerInventoryRepository(data_store, unit_of_work)
        status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        item_repo = InMemoryItemRepository(data_store, unit_of_work)
        spec_repo = InMemoryItemSpecRepository()
        return map_repo, inv_repo, status_repo, item_repo, spec_repo

    @pytest.fixture
    def service(self, repos, unit_of_work):
        map_repo, inv_repo, status_repo, item_repo, spec_repo = repos
        return PlaceObjectApplicationService(
            physical_map_repository=map_repo,
            player_inventory_repository=inv_repo,
            player_status_repository=status_repo,
            item_repository=item_repo,
            item_spec_repository=spec_repo,
            unit_of_work=unit_of_work,
        )

    @pytest.fixture
    def map_with_player(self, repos):
        map_repo, inv_repo, status_repo, item_repo, spec_repo = repos
        spot_id = SpotId(1)
        pmap = _create_map(1)
        player_id_val = 1
        actor_id = WorldObjectId(player_id_val)
        actor = WorldObject(
            actor_id,
            Coordinate(1, 1, 0),
            ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(direction=DirectionEnum.SOUTH),
        )
        pmap.add_object(actor)
        map_repo.save(pmap)
        exp_table = ExpTable(100, 1.5)
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
            current_spot_id=spot_id,
            current_coordinate=Coordinate(1, 1, 0),
        )
        status_repo.save(status)
        return pmap, actor_id, player_id_val

    @pytest.fixture
    def placeable_item_in_slot0(self, repos, map_with_player):
        map_repo, inv_repo, status_repo, item_repo, spec_repo = repos
        pmap, actor_id, player_id_val = map_with_player
        spec = _placeable_chest_spec()
        spec_rm = ItemSpecReadModel(
            item_spec_id=spec.item_spec_id,
            name=spec.name,
            item_type=spec.item_type,
            rarity=spec.rarity,
            description=spec.description,
            max_stack_size=spec.max_stack_size,
            is_placeable=spec.is_placeable,
            placeable_object_type=spec.placeable_object_type,
        )
        spec_repo.save(spec_rm)
        item_instance_id = item_repo.generate_item_instance_id()
        item_agg = ItemAggregate.create(item_instance_id, spec, durability=None, quantity=1)
        item_repo.save(item_agg)
        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(player_id_val))
        inv.acquire_item(item_instance_id)
        inv_repo.save(inv)
        return item_instance_id, player_id_val

    def test_place_object_success(self, service, repos, map_with_player, placeable_item_in_slot0):
        """設置成功: スロット0の設置可能アイテムがプレイヤー前方に設置され、インベントリから減ること"""
        map_repo, inv_repo, status_repo, item_repo, spec_repo = repos
        pmap, actor_id, player_id_val = map_with_player
        item_instance_id, _ = placeable_item_in_slot0

        service.place_object(PlaceObjectCommand(player_id=player_id_val, spot_id=1, inventory_slot_id=0))

        pmap = map_repo.find_by_spot_id(SpotId(1))
        front = Coordinate(1, 2, 0)
        objs_at_front = pmap.get_objects_at(front)
        assert len(objs_at_front) == 1
        placed = objs_at_front[0]
        assert placed.object_type == ObjectTypeEnum.CHEST
        assert isinstance(placed.component, PlaceableComponent)
        assert placed.component.get_drop_item_spec_id() == ItemSpecId(900)

        inv = inv_repo.find_by_id(PlayerId(player_id_val))
        assert inv.get_item_instance_id_by_slot(SlotId(0)) is None

    def test_place_object_no_item_in_slot_raises(self, service, repos, map_with_player):
        """スロットにアイテムがない場合は NoItemInSlotException"""
        map_repo, inv_repo, status_repo, item_repo, spec_repo = repos
        pmap, actor_id, player_id_val = map_with_player
        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(player_id_val))
        inv_repo.save(inv)
        exp_table = ExpTable(100, 1.5)
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
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(1, 1, 0),
        )
        status_repo.save(status)

        with pytest.raises(NoItemInSlotException):
            service.place_object(PlaceObjectCommand(player_id=player_id_val, spot_id=1, inventory_slot_id=0))

    def test_place_object_not_placeable_raises(self, service, repos, map_with_player):
        """設置可能でないアイテムの場合は ItemNotPlaceableException"""
        map_repo, inv_repo, status_repo, item_repo, spec_repo = repos
        pmap, actor_id, player_id_val = map_with_player
        non_placeable_spec = ItemSpec(
            item_spec_id=ItemSpecId(901),
            name="Potion",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="Heals",
            max_stack_size=MaxStackSize(10),
            is_placeable=False,
            placeable_object_type=None,
        )
        item_instance_id = item_repo.generate_item_instance_id()
        item_agg = ItemAggregate.create(item_instance_id, non_placeable_spec, durability=None, quantity=1)
        item_repo.save(item_agg)
        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(player_id_val))
        inv.acquire_item(item_instance_id)
        inv_repo.save(inv)

        with pytest.raises(ItemNotPlaceableException):
            service.place_object(PlaceObjectCommand(player_id=player_id_val, spot_id=1, inventory_slot_id=0))

    def test_place_object_blocked_raises(self, service, repos, map_with_player, placeable_item_in_slot0):
        """前方がブロックされている場合は PlacementBlockedException"""
        map_repo, inv_repo, status_repo, item_repo, spec_repo = repos
        pmap, actor_id, player_id_val = map_with_player
        placeable_item_in_slot0
        front = Coordinate(1, 2, 0)
        wall = WorldObject(WorldObjectId(999), front, ObjectTypeEnum.CHEST, is_blocking=True, component=ChestComponent())
        pmap = map_repo.find_by_spot_id(SpotId(1))
        pmap.add_object(wall)
        map_repo.save(pmap)

        with pytest.raises(PlacementBlockedException):
            service.place_object(PlaceObjectCommand(player_id=player_id_val, spot_id=1, inventory_slot_id=0))

    def test_destroy_placeable_success(self, service, repos, map_with_player, placeable_item_in_slot0):
        """破壊成功: 前方の設置物が消え、アイテムがインベントリに追加されること"""
        map_repo, inv_repo, status_repo, item_repo, spec_repo = repos
        pmap, actor_id, player_id_val = map_with_player
        placeable_item_in_slot0
        service.place_object(PlaceObjectCommand(player_id=player_id_val, spot_id=1, inventory_slot_id=0))

        service.destroy_placeable(DestroyPlaceableCommand(player_id=player_id_val, spot_id=1))

        pmap = map_repo.find_by_spot_id(SpotId(1))
        front = Coordinate(1, 2, 0)
        objs = pmap.get_objects_at(front)
        assert len(objs) == 0
        inv = inv_repo.find_by_id(PlayerId(player_id_val))
        has_item = any(inv.get_item_instance_id_by_slot(SlotId(i)) is not None for i in range(inv.max_slots))
        assert has_item

    def test_destroy_placeable_nothing_in_front_raises(self, service, repos, map_with_player):
        """前方に設置物がない場合は NoPlaceableInFrontException"""
        map_repo, inv_repo, status_repo, item_repo, spec_repo = repos
        pmap, actor_id, player_id_val = map_with_player

        with pytest.raises(NoPlaceableInFrontException):
            service.destroy_placeable(DestroyPlaceableCommand(player_id=player_id_val, spot_id=1))
