import pytest
from src.domain.item.item_quantity import ItemQuantity
from src.domain.item.unique_item import UniqueItem
from src.domain.item.consumable_item import ConsumableItem
from src.domain.item.item_enum import ItemType, Rarity
from src.domain.item.item_effect import HealEffect
from src.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from src.domain.player.value_object.player_id import PlayerId
from src.domain.player.value_object.player_inventory_id import PlayerInventoryId
from src.domain.player.value_object.inventory_slots import InventorySlots
from src.domain.player.event.inventory_events import ItemAddedToInventoryEvent, ItemRemovedFromInventoryEvent


# テスト用のアイテム作成ヘルパー関数
def create_test_consumable_item(item_id: int, name: str) -> ConsumableItem:
    """テスト用のConsumableItemを作成"""
    effect = HealEffect(50)
    return ConsumableItem(
        item_id=item_id,
        name=name,
        description="Test consumable item",
        item_type=ItemType.CONSUMABLE,
        rarity=Rarity.COMMON,
        effect=effect
    )


def create_test_unique_item(unique_id: int, item_id: int, name: str) -> UniqueItem:
    """テスト用のUniqueItemを作成"""
    return UniqueItem(
        unique_id=unique_id,
        item_id=item_id,
        name=name,
        description="Test unique item",
        item_type=ItemType.WEAPON,
        rarity=Rarity.COMMON
    )


class TestPlayerInventoryAggregate:
    """PlayerInventoryAggregateのテスト"""

    @pytest.fixture
    def sample_inventory(self) -> PlayerInventoryAggregate:
        """テスト用のインベントリを作成"""
        inventory_id = PlayerInventoryId(1)
        player_id = PlayerId(100)
        return PlayerInventoryAggregate.create_new_inventory(inventory_id, player_id, max_slots=5)

    def test_create_new_inventory(self):
        """新しいインベントリを作成できること"""
        inventory_id = PlayerInventoryId(1)
        player_id = PlayerId(100)

        inventory = PlayerInventoryAggregate.create_new_inventory(inventory_id, player_id, max_slots=10)

        assert inventory.inventory_id == inventory_id
        assert inventory.player_id == player_id
        assert inventory.max_slots == 10
        assert inventory.free_slots_count == 10
        assert not inventory.is_full()

    def test_add_stackable_item(self, sample_inventory):
        """スタック可能アイテムを追加できること"""
        consumable_item = create_test_consumable_item(1, "Test Item")
        item = ItemQuantity(item=consumable_item, quantity=5)

        sample_inventory.add_item(item)

        assert sample_inventory.has_stackable(1, 5)
        assert sample_inventory.get_total_quantity(1) == 5
        assert sample_inventory.free_slots_count == 4

        # イベントが発行されていることを確認
        events = sample_inventory.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, ItemAddedToInventoryEvent)
        assert event.player_id == 100
        assert event.item_id == 1
        assert event.quantity == 5
        assert event.aggregate_id == sample_inventory.inventory_id
        assert event.aggregate_type == "PlayerInventoryAggregate"

    def test_add_unique_item(self, sample_inventory):
        """ユニークアイテムを追加できること"""
        item = create_test_unique_item(200, 1, "Test Unique")

        sample_inventory.add_item(item)

        assert sample_inventory.has_unique(200)
        assert sample_inventory.free_slots_count == 4

        # イベントが発行されていることを確認
        events = sample_inventory.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, ItemAddedToInventoryEvent)
        assert event.player_id == 100
        assert event.item_id == 1
        assert event.unique_id == 200
        assert event.aggregate_id == sample_inventory.inventory_id
        assert event.aggregate_type == "PlayerInventoryAggregate"

    def test_stack_same_item_type(self, sample_inventory):
        """同じ種類のアイテムをスタックできること"""
        consumable_item = create_test_consumable_item(1, "Test Item")
        item1 = ItemQuantity(item=consumable_item, quantity=3)
        item2 = ItemQuantity(item=consumable_item, quantity=7)

        sample_inventory.add_item(item1)
        sample_inventory.add_item(item2)

        assert sample_inventory.get_total_quantity(1) == 10
        assert sample_inventory.free_slots_count == 4  # 1スロットのみ使用

    def test_add_item_to_full_inventory_raises_error(self, sample_inventory):
        """満杯のインベントリにはアイテムを追加できないこと"""
        # 5つのスロットを埋める
        for i in range(5):
            item = create_test_unique_item(i + 100, 1, f"Test Unique {i}")
            sample_inventory.add_item(item)

        # 6つ目のアイテムを追加しようとする
        item6 = create_test_unique_item(200, 1, "Test Unique 6")
        with pytest.raises(ValueError):
            sample_inventory.add_item(item6)

    def test_remove_stackable_item(self, sample_inventory):
        """スタック可能アイテムを削除できること"""
        item = ItemQuantity(item=create_test_consumable_item(1, "Test Item"), quantity=10)
        sample_inventory.add_item(item)

        # 5個削除
        removed = sample_inventory.remove_item(item_id=1, quantity=5)

        assert removed.quantity == 5
        assert sample_inventory.get_total_quantity(1) == 5

        # イベントが発行されていることを確認
        events = sample_inventory.get_events()
        assert len(events) == 2  # add + remove
        event = events[1]
        assert isinstance(event, ItemRemovedFromInventoryEvent)
        assert event.item_id == 1
        assert event.quantity == 5

    def test_remove_unique_item(self, sample_inventory):
        """ユニークアイテムを削除できること"""
        item = create_test_unique_item(200, 1, "Test Unique")
        sample_inventory.add_item(item)

        removed = sample_inventory.remove_item(unique_id=200)

        assert removed.unique_id == 200
        assert not sample_inventory.has_unique(200)

        # イベントが発行されていることを確認
        events = sample_inventory.get_events()
        assert len(events) == 2  # add + remove
        event = events[1]
        assert isinstance(event, ItemRemovedFromInventoryEvent)
        assert event.unique_id == 200

    def test_remove_nonexistent_item_returns_none(self, sample_inventory):
        """存在しないアイテムの削除はNoneを返すこと"""
        removed = sample_inventory.remove_item(item_id=999)

        assert removed is None

        # イベントは発行されない
        events = sample_inventory.get_events()
        assert len(events) == 0

    def test_can_add_item_check(self, sample_inventory):
        """アイテム追加可能かどうかのチェックが正しく動作すること"""
        item = ItemQuantity(item=create_test_consumable_item(1, "Test Item"), quantity=5)

        assert sample_inventory.can_add_item(item)

        # 満杯にする
        for i in range(5):
            unique_item = create_test_unique_item(i + 100, 2, f"Test Unique {i}")
            sample_inventory.add_item(unique_item)

        assert not sample_inventory.can_add_item(item)

    def test_get_slot_by_id(self, sample_inventory):
        """スロットIDでスロットを取得できること"""
        item = ItemQuantity(item=create_test_consumable_item(1, "Test Item"), quantity=5)
        sample_inventory.add_item(item)

        slot = sample_inventory.get_slot_by_id(0)
        assert slot is not None
        assert slot.is_stackable()

        # 存在しないスロット
        slot = sample_inventory.get_slot_by_id(10)
        assert slot is None
