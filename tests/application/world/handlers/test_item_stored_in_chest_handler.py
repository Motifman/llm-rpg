"""ItemStoredInChestHandler のテスト"""

import pytest
from ai_rpg_world.application.world.handlers.item_stored_in_chest_handler import (
    ItemStoredInChestHandler,
)
from ai_rpg_world.domain.world.event.map_events import ItemStoredInChestEvent
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)


class _FakeUow:
    pass


class TestItemStoredInChestHandler:
    """ItemStoredInChestHandler の正常・スキップ・例外ケース"""

    @pytest.fixture
    def inventory_repo(self):
        return InMemoryPlayerInventoryRepository()

    @pytest.fixture
    def handler(self, inventory_repo):
        return ItemStoredInChestHandler(inventory_repo, _FakeUow())

    def test_removes_item_from_player_inventory(self, handler, inventory_repo):
        """収納イベントでプレイヤーインベントリからアイテムが削除されること"""
        player_id = PlayerId.create(1)
        inventory = PlayerInventoryAggregate.create_new_inventory(player_id)
        item_id = ItemInstanceId.create(100)
        inventory.acquire_item(item_id)
        inventory_repo.save(inventory)
        assert inventory.has_item(item_id) is True

        event = ItemStoredInChestEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="PhysicalMap",
            spot_id=SpotId(1),
            chest_id=WorldObjectId.create(2),
            actor_id=WorldObjectId.create(10),
            item_instance_id=item_id,
            player_id_value=1,
        )
        handler.handle(event)

        loaded = inventory_repo.find_by_id(player_id)
        assert loaded.has_item(item_id) is False

    def test_skips_when_inventory_not_found(self, handler, inventory_repo):
        """インベントリが見つからない場合はスキップ（例外にならない）"""
        event = ItemStoredInChestEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="PhysicalMap",
            spot_id=SpotId(1),
            chest_id=WorldObjectId.create(2),
            actor_id=WorldObjectId.create(10),
            item_instance_id=ItemInstanceId.create(999),
            player_id_value=99999,
        )
        handler.handle(event)
        # スキップされるだけなので何も起きない

    def test_raises_when_item_not_in_inventory(self, handler, inventory_repo):
        """インベントリにアイテムがない場合はドメイン例外が伝播する"""
        player_id = PlayerId.create(1)
        inventory = PlayerInventoryAggregate.create_new_inventory(player_id)
        inventory_repo.save(inventory)
        item_id = ItemInstanceId.create(100)
        assert not inventory.has_item(item_id)

        event = ItemStoredInChestEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="PhysicalMap",
            spot_id=SpotId(1),
            chest_id=WorldObjectId.create(2),
            actor_id=WorldObjectId.create(10),
            item_instance_id=item_id,
            player_id_value=1,
        )
        from ai_rpg_world.domain.player.exception.player_exceptions import ItemNotInSlotException
        with pytest.raises(ItemNotInSlotException):
            handler.handle(event)
