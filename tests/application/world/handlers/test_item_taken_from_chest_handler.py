"""ItemTakenFromChestHandler のテスト"""

import pytest
from ai_rpg_world.application.world.handlers.item_taken_from_chest_handler import (
    ItemTakenFromChestHandler,
)
from ai_rpg_world.domain.world.event.map_events import ItemTakenFromChestEvent
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


class TestItemTakenFromChestHandler:
    """ItemTakenFromChestHandler の正常・スキップケース"""

    @pytest.fixture
    def inventory_repo(self):
        return InMemoryPlayerInventoryRepository()

    @pytest.fixture
    def handler(self, inventory_repo):
        return ItemTakenFromChestHandler(inventory_repo, _FakeUow())

    def test_adds_item_to_player_inventory(self, handler, inventory_repo):
        """取得イベントでプレイヤーインベントリにアイテムが追加されること"""
        player_id = PlayerId.create(1)
        inventory = PlayerInventoryAggregate.create_new_inventory(player_id)
        inventory_repo.save(inventory)
        item_id = ItemInstanceId.create(100)
        assert not inventory.has_item(item_id)

        event = ItemTakenFromChestEvent.create(
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
        assert loaded.has_item(item_id) is True

    def test_skips_when_inventory_not_found(self, handler, inventory_repo):
        """インベントリが見つからない場合はスキップ（例外にならない）"""
        event = ItemTakenFromChestEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="PhysicalMap",
            spot_id=SpotId(1),
            chest_id=WorldObjectId.create(2),
            actor_id=WorldObjectId.create(10),
            item_instance_id=ItemInstanceId.create(100),
            player_id_value=99999,
        )
        handler.handle(event)
