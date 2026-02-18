"""ChestCommandService の正常・例外ケースの網羅的テスト"""

import pytest
from ai_rpg_world.application.world.services.chest_command_service import ChestCommandService
from ai_rpg_world.application.world.contracts.commands import (
    StoreItemInChestCommand,
    TakeItemFromChestCommand,
)
from ai_rpg_world.application.world.exceptions.command.chest_command_exception import (
    ChestCommandException,
    ChestNotFoundException,
    ItemNotInPlayerInventoryException,
    PlayerInventoryNotFoundException,
    ItemNotInChestCommandException,
)
from ai_rpg_world.application.world.exceptions.base_exception import WorldSystemErrorException
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    ChestComponent,
    InteractableComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import (
    ObjectTypeEnum,
    DirectionEnum,
    InteractionTypeEnum,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.application.world.handlers.item_stored_in_chest_handler import ItemStoredInChestHandler
from ai_rpg_world.application.world.handlers.item_taken_from_chest_handler import ItemTakenFromChestHandler
from ai_rpg_world.infrastructure.events.map_interaction_event_handler_registry import MapInteractionEventHandlerRegistry
from ai_rpg_world.domain.world.exception.map_exception import MapDomainException
from unittest.mock import patch


def _create_map(spot_id_int: int = 1) -> PhysicalMapAggregate:
    tiles = [
        Tile(Coordinate(x, y, 0), TerrainType.road())
        for x in range(5)
        for y in range(5)
    ]
    return PhysicalMapAggregate.create(SpotId(spot_id_int), tiles)


class TestChestCommandService:
    """ChestCommandService の正常・例外ケース"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def unit_of_work(self, data_store):
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)
        uow, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )
        inventory_repo = InMemoryPlayerInventoryRepository(data_store, uow)
        map_repo = InMemoryPhysicalMapRepository(data_store, uow)
        item_stored_handler = ItemStoredInChestHandler(inventory_repo, uow)
        item_taken_handler = ItemTakenFromChestHandler(inventory_repo, uow)
        registry = MapInteractionEventHandlerRegistry(
            item_stored_in_chest_handler=item_stored_handler,
            item_taken_from_chest_handler=item_taken_handler,
        )
        registry.register_handlers(event_publisher)
        uow._event_publisher = event_publisher
        return uow, map_repo, inventory_repo

    @pytest.fixture
    def service(self, unit_of_work):
        uow, map_repo, inventory_repo = unit_of_work
        return ChestCommandService(
            physical_map_repository=map_repo,
            player_inventory_repository=inventory_repo,
            unit_of_work=uow,
        )

    @pytest.fixture
    def map_with_chest_and_actor(self, unit_of_work):
        uow, map_repo, inventory_repo = unit_of_work
        pmap = _create_map(1)
        actor_id = WorldObjectId(1)
        chest_id = WorldObjectId(2)
        actor = WorldObject(
            actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH),
        )
        chest = WorldObject(
            chest_id, Coordinate(0, 1, 0), ObjectTypeEnum.CHEST,
            component=ChestComponent(is_open=True),
        )
        pmap.add_object(actor)
        pmap.add_object(chest)
        map_repo.save(pmap)
        return pmap, actor_id, chest_id

    def test_store_item_in_chest_success(self, service, unit_of_work, map_with_chest_and_actor):
        """収納成功: マップのチェストにアイテムが入り、インベントリから削除されること"""
        uow, map_repo, inventory_repo = unit_of_work
        pmap, actor_id, chest_id = map_with_chest_and_actor
        player_id = PlayerId.create(1)
        inventory = PlayerInventoryAggregate.create_new_inventory(player_id)
        item_id = ItemInstanceId.create(100)
        inventory.acquire_item(item_id)
        inventory_repo.save(inventory)
        assert inventory.has_item(item_id) is True

        command = StoreItemInChestCommand(
            player_id=1,
            spot_id=1,
            actor_world_object_id=1,
            chest_world_object_id=2,
            item_instance_id=100,
        )
        service.store_item_in_chest(command)

        loaded_map = map_repo.find_by_spot_id(SpotId(1))
        chest_obj = loaded_map.get_object(chest_id)
        assert chest_obj.component.has_item(item_id) is True
        loaded_inv = inventory_repo.find_by_id(player_id)
        assert loaded_inv.has_item(item_id) is False

    def test_store_item_in_chest_raises_when_map_not_found(self, service, unit_of_work):
        """マップが見つからない場合は ChestNotFoundException"""
        uow, map_repo, inventory_repo = unit_of_work
        player_id = PlayerId.create(1)
        inv = PlayerInventoryAggregate.create_new_inventory(player_id)
        inv.acquire_item(ItemInstanceId.create(100))
        inventory_repo.save(inv)
        command = StoreItemInChestCommand(
            player_id=1,
            spot_id=999,
            actor_world_object_id=1,
            chest_world_object_id=2,
            item_instance_id=100,
        )
        with pytest.raises(ChestNotFoundException):
            service.store_item_in_chest(command)

    def test_store_item_in_chest_raises_when_item_not_in_inventory(
        self, service, unit_of_work, map_with_chest_and_actor
    ):
        """プレイヤーがアイテムを所持していない場合は ItemNotInPlayerInventoryException"""
        uow, map_repo, inventory_repo = unit_of_work
        pmap, actor_id, chest_id = map_with_chest_and_actor
        player_id = PlayerId.create(1)
        inventory = PlayerInventoryAggregate.create_new_inventory(player_id)
        inventory_repo.save(inventory)
        assert not inventory.has_item(ItemInstanceId.create(100))

        command = StoreItemInChestCommand(
            player_id=1,
            spot_id=1,
            actor_world_object_id=1,
            chest_world_object_id=2,
            item_instance_id=100,
        )
        with pytest.raises(ItemNotInPlayerInventoryException):
            service.store_item_in_chest(command)

    def test_store_item_in_chest_raises_when_inventory_not_found(
        self, service, unit_of_work, map_with_chest_and_actor
    ):
        """プレイヤーインベントリが存在しない場合は PlayerInventoryNotFoundException"""
        uow, map_repo, inventory_repo = unit_of_work
        pmap, actor_id, chest_id = map_with_chest_and_actor
        # インベントリは登録しない（player_id=1 のインベントリがない）
        command = StoreItemInChestCommand(
            player_id=1,
            spot_id=1,
            actor_world_object_id=1,
            chest_world_object_id=2,
            item_instance_id=100,
        )
        with pytest.raises(PlayerInventoryNotFoundException):
            service.store_item_in_chest(command)

    def test_take_item_from_chest_success(self, service, unit_of_work, map_with_chest_and_actor):
        """取得成功: チェストからアイテムが減り、インベントリに追加されること"""
        uow, map_repo, inventory_repo = unit_of_work
        pmap, actor_id, chest_id = map_with_chest_and_actor
        item_id = ItemInstanceId.create(50)
        chest_obj = pmap.get_object(chest_id)
        chest_obj.component.add_item(item_id)
        map_repo.save(pmap)
        player_id = PlayerId.create(1)
        inventory = PlayerInventoryAggregate.create_new_inventory(player_id)
        inventory_repo.save(inventory)
        assert not inventory.has_item(item_id)

        command = TakeItemFromChestCommand(
            player_id=1,
            spot_id=1,
            actor_world_object_id=1,
            chest_world_object_id=2,
            item_instance_id=50,
        )
        service.take_item_from_chest(command)

        loaded_map = map_repo.find_by_spot_id(SpotId(1))
        chest_after = loaded_map.get_object(chest_id)
        assert chest_after.component.has_item(item_id) is False
        loaded_inv = inventory_repo.find_by_id(player_id)
        assert loaded_inv.has_item(item_id) is True

    def test_take_item_from_chest_raises_when_map_not_found(self, service, unit_of_work):
        """マップが見つからない場合は ChestNotFoundException"""
        uow, map_repo, inventory_repo = unit_of_work
        player_id = PlayerId.create(1)
        inv = PlayerInventoryAggregate.create_new_inventory(player_id)
        inventory_repo.save(inv)
        command = TakeItemFromChestCommand(
            player_id=1,
            spot_id=999,
            actor_world_object_id=1,
            chest_world_object_id=2,
            item_instance_id=50,
        )
        with pytest.raises(ChestNotFoundException):
            service.take_item_from_chest(command)

    def test_store_item_in_chest_raises_when_chest_object_not_on_map(
        self, service, unit_of_work, map_with_chest_and_actor
    ):
        """マップは存在するがチェストオブジェクトがマップ上にない場合は ChestNotFoundException"""
        uow, map_repo, inventory_repo = unit_of_work
        pmap, actor_id, chest_id = map_with_chest_and_actor
        player_id = PlayerId.create(1)
        inv = PlayerInventoryAggregate.create_new_inventory(player_id)
        inv.acquire_item(ItemInstanceId.create(100))
        inventory_repo.save(inv)
        command = StoreItemInChestCommand(
            player_id=1,
            spot_id=1,
            actor_world_object_id=1,
            chest_world_object_id=99,
            item_instance_id=100,
        )
        with pytest.raises(ChestNotFoundException):
            service.store_item_in_chest(command)

    def test_take_item_from_chest_raises_when_chest_object_not_on_map(
        self, service, unit_of_work, map_with_chest_and_actor
    ):
        """マップは存在するがチェストオブジェクトがマップ上にない場合は ChestNotFoundException"""
        uow, map_repo, inventory_repo = unit_of_work
        pmap, actor_id, chest_id = map_with_chest_and_actor
        player_id = PlayerId.create(1)
        inv = PlayerInventoryAggregate.create_new_inventory(player_id)
        inventory_repo.save(inv)
        command = TakeItemFromChestCommand(
            player_id=1,
            spot_id=1,
            actor_world_object_id=1,
            chest_world_object_id=99,
            item_instance_id=50,
        )
        with pytest.raises(ChestNotFoundException):
            service.take_item_from_chest(command)

    def test_take_item_from_chest_raises_when_item_not_in_chest(
        self, service, unit_of_work, map_with_chest_and_actor
    ):
        """チェストに指定アイテムが存在しない場合は ItemNotInChestCommandException"""
        uow, map_repo, inventory_repo = unit_of_work
        pmap, actor_id, chest_id = map_with_chest_and_actor
        player_id = PlayerId.create(1)
        inv = PlayerInventoryAggregate.create_new_inventory(player_id)
        inventory_repo.save(inv)
        command = TakeItemFromChestCommand(
            player_id=1,
            spot_id=1,
            actor_world_object_id=1,
            chest_world_object_id=2,
            item_instance_id=50,
        )
        with pytest.raises(ItemNotInChestCommandException):
            service.take_item_from_chest(command)

    def test_store_item_in_chest_command_validation(self):
        """StoreItemInChestCommand のバリデーション"""
        with pytest.raises(ValueError):
            StoreItemInChestCommand(
                player_id=0,
                spot_id=1,
                actor_world_object_id=1,
                chest_world_object_id=2,
                item_instance_id=100,
            )
        with pytest.raises(ValueError):
            StoreItemInChestCommand(
                player_id=1,
                spot_id=0,
                actor_world_object_id=1,
                chest_world_object_id=2,
                item_instance_id=100,
            )
        with pytest.raises(ValueError):
            StoreItemInChestCommand(
                player_id=1,
                spot_id=1,
                actor_world_object_id=0,
                chest_world_object_id=2,
                item_instance_id=100,
            )
        with pytest.raises(ValueError):
            StoreItemInChestCommand(
                player_id=1,
                spot_id=1,
                actor_world_object_id=1,
                chest_world_object_id=0,
                item_instance_id=100,
            )
        with pytest.raises(ValueError):
            StoreItemInChestCommand(
                player_id=1,
                spot_id=1,
                actor_world_object_id=1,
                chest_world_object_id=2,
                item_instance_id=0,
            )

    def test_take_item_from_chest_command_validation(self):
        """TakeItemFromChestCommand のバリデーション"""
        with pytest.raises(ValueError):
            TakeItemFromChestCommand(
                player_id=0,
                spot_id=1,
                actor_world_object_id=1,
                chest_world_object_id=2,
                item_instance_id=50,
            )
        with pytest.raises(ValueError):
            TakeItemFromChestCommand(
                player_id=1,
                spot_id=0,
                actor_world_object_id=1,
                chest_world_object_id=2,
                item_instance_id=50,
            )
        with pytest.raises(ValueError):
            TakeItemFromChestCommand(
                player_id=1,
                spot_id=1,
                actor_world_object_id=0,
                chest_world_object_id=2,
                item_instance_id=50,
            )
        with pytest.raises(ValueError):
            TakeItemFromChestCommand(
                player_id=1,
                spot_id=1,
                actor_world_object_id=1,
                chest_world_object_id=0,
                item_instance_id=50,
            )
        with pytest.raises(ValueError):
            TakeItemFromChestCommand(
                player_id=1,
                spot_id=1,
                actor_world_object_id=1,
                chest_world_object_id=2,
                item_instance_id=0,
            )

    def test_execute_with_error_handling_domain_exception(self, service, unit_of_work, map_with_chest_and_actor):
        """操作中にドメイン例外が発生した場合は ChestCommandException に変換される"""
        uow, map_repo, inventory_repo = unit_of_work
        pmap, actor_id, chest_id = map_with_chest_and_actor
        player_id = PlayerId.create(1)
        inv = PlayerInventoryAggregate.create_new_inventory(player_id)
        inv.acquire_item(ItemInstanceId.create(100))
        inventory_repo.save(inv)
        command = StoreItemInChestCommand(
            player_id=1,
            spot_id=1,
            actor_world_object_id=1,
            chest_world_object_id=2,
            item_instance_id=100,
        )
        with patch.object(
            pmap.__class__,
            "store_item_in_chest",
            side_effect=MapDomainException("test domain error"),
        ):
            with pytest.raises(ChestCommandException) as exc_info:
                service.store_item_in_chest(command)
            assert "test domain error" in str(exc_info.value)

    def test_execute_with_error_handling_unexpected_exception(self, service, unit_of_work, map_with_chest_and_actor):
        """操作中に想定外の例外が発生した場合は WorldSystemErrorException"""
        uow, map_repo, inventory_repo = unit_of_work
        pmap, actor_id, chest_id = map_with_chest_and_actor
        player_id = PlayerId.create(1)
        inv = PlayerInventoryAggregate.create_new_inventory(player_id)
        inv.acquire_item(ItemInstanceId.create(100))
        inventory_repo.save(inv)
        command = StoreItemInChestCommand(
            player_id=1,
            spot_id=1,
            actor_world_object_id=1,
            chest_world_object_id=2,
            item_instance_id=100,
        )
        with patch.object(
            pmap.__class__,
            "store_item_in_chest",
            side_effect=RuntimeError("unexpected"),
        ):
            with pytest.raises(WorldSystemErrorException) as exc_info:
                service.store_item_in_chest(command)
            assert exc_info.value.original_exception is not None
            assert isinstance(exc_info.value.original_exception, RuntimeError)
