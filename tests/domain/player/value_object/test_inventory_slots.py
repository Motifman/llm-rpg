import pytest
from src.domain.item.item_quantity import ItemQuantity
from src.domain.item.unique_item import UniqueItem
from src.domain.item.consumable_item import ConsumableItem
from src.domain.item.item_enum import ItemType, Rarity
from src.domain.item.item_effect import HealEffect
from src.domain.player.value_object.inventory_slots import InventorySlots, InventorySlot


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


class TestInventorySlot:
    """InventorySlot値オブジェクトのテスト"""

    def test_create_empty_slot(self):
        """空のスロットを作成できること"""
        slot = InventorySlot.create_empty(0)
        assert slot.slot_id == 0
        assert slot.is_empty()
        assert not slot.is_stackable()
        assert not slot.is_unique()

    def test_invalid_slot_id_raises_error(self):
        """無効なslot_idは作成できないこと"""
        with pytest.raises(ValueError):
            InventorySlot(slot_id=-1)

    def test_add_stackable_to_empty_slot(self):
        """空のスロットにスタック可能アイテムを追加できること"""
        slot = InventorySlot.create_empty(0)
        consumable_item = create_test_consumable_item(1, "Test Item")
        item = ItemQuantity(item=consumable_item, quantity=5)

        new_slot = slot.with_stackable_added(item)
        assert new_slot.slot_id == 0
        assert new_slot.is_stackable()
        assert new_slot.content.quantity == 5

    def test_add_unique_to_empty_slot(self):
        """空のスロットにユニークアイテムを追加できること"""
        slot = InventorySlot.create_empty(0)
        item = create_test_unique_item(100, 1, "Test Unique")

        new_slot = slot.with_unique_added(item)
        assert new_slot.slot_id == 0
        assert new_slot.is_unique()
        assert new_slot.content.unique_id == 100

    def test_add_unique_to_occupied_slot_raises_error(self):
        """占有されているスロットにユニークアイテムを追加できないこと"""
        item1 = create_test_unique_item(100, 1, "Test Unique 1")
        slot = InventorySlot(slot_id=0, content=item1)

        item2 = create_test_unique_item(200, 2, "Test Unique 2")
        with pytest.raises(ValueError):
            slot.with_unique_added(item2)

    def test_stack_same_item_type(self):
        """同じ種類のスタック可能アイテムをスタックできること"""
        consumable_item = create_test_consumable_item(1, "Test Item")
        item1 = ItemQuantity(item=consumable_item, quantity=5)
        item2 = ItemQuantity(item=consumable_item, quantity=3)
        slot = InventorySlot(slot_id=0, content=item1)

        new_slot = slot.with_stackable_added(item2)
        assert new_slot.content.quantity == 8

    def test_stack_different_item_type_raises_error(self):
        """異なる種類のスタック可能アイテムはスタックできないこと"""
        item1 = ItemQuantity(item=create_test_consumable_item(1, "Test Item 1"), quantity=5)
        item2 = ItemQuantity(item=create_test_consumable_item(2, "Test Item 2"), quantity=3)
        slot = InventorySlot(slot_id=0, content=item1)

        with pytest.raises(ValueError):
            slot.with_stackable_added(item2)

    def test_stack_exceed_max_size_raises_error(self):
        """最大スタックサイズを超えるスタックはできないこと"""
        consumable_item = create_test_consumable_item(1, "Test Item")
        item1 = ItemQuantity(item=consumable_item, quantity=95)
        item2 = ItemQuantity(item=consumable_item, quantity=10)
        slot = InventorySlot(slot_id=0, content=item1)

        with pytest.raises(ValueError):
            slot.with_stackable_added(item2)

    def test_remove_item_from_slot(self):
        """スロットからアイテムを削除できること"""
        item = ItemQuantity(item=create_test_consumable_item(1, "Test Item"), quantity=5)
        slot = InventorySlot(slot_id=0, content=item)

        new_slot = slot.with_item_removed()
        assert new_slot.is_empty()


class TestInventorySlots:
    """InventorySlots値オブジェクトのテスト"""

    def test_create_empty_inventory(self):
        """空のインベントリを作成できること"""
        slots = InventorySlots.create_empty(5)
        assert len(slots.slots) == 5
        assert slots.max_slots == 5
        assert all(slot.is_empty() for slot in slots.slots)

    def test_too_many_slots_raises_error(self):
        """max_slotsを超えるスロット数は作成できないこと"""
        with pytest.raises(ValueError):
            InventorySlots(slots=[InventorySlot.create_empty(i) for i in range(10)], max_slots=5)

    def test_add_stackable_item_to_empty_inventory(self):
        """空のインベントリにスタック可能アイテムを追加できること"""
        slots = InventorySlots.create_empty(5)
        item = ItemQuantity(item=create_test_consumable_item(1, "Test Item"), quantity=5)

        new_slots = slots.with_item_added(item)
        assert not new_slots.is_full()
        assert new_slots.get_free_slots_count() == 4

        # 最初のスロットにアイテムが追加されていることを確認
        first_slot = new_slots.get_slot_by_id(0)
        assert first_slot.is_stackable()
        assert first_slot.content.quantity == 5

    def test_add_unique_item_to_inventory(self):
        """インベントリにユニークアイテムを追加できること"""
        slots = InventorySlots.create_empty(5)
        item = create_test_unique_item(100, 1, "Test Unique")

        new_slots = slots.with_item_added(item)

        # 最初のスロットにアイテムが追加されていることを確認
        first_slot = new_slots.get_slot_by_id(0)
        assert first_slot.is_unique()
        assert first_slot.content.unique_id == 100

    def test_stack_same_item_type_in_inventory(self):
        """同じ種類のアイテムをスタックできること"""
        slots = InventorySlots.create_empty(5)
        consumable_item = create_test_consumable_item(1, "Test Item")
        item1 = ItemQuantity(item=consumable_item, quantity=5)
        item2 = ItemQuantity(item=consumable_item, quantity=3)

        slots = slots.with_item_added(item1)
        slots = slots.with_item_added(item2)

        total_quantity = slots.get_total_quantity_by_item_id(1)
        assert total_quantity == 8

    def test_add_item_to_full_inventory_raises_error(self):
        """満杯のインベントリにはアイテムを追加できないこと"""
        slots = InventorySlots.create_empty(1)  # 1スロットのみ
        item1 = create_test_unique_item(100, 1, "Test Unique 1")
        item2 = create_test_unique_item(200, 2, "Test Unique 2")

        slots = slots.with_item_added(item1)  # 1スロットを占有

        with pytest.raises(ValueError):
            slots.with_item_added(item2)  # 追加できない

    def test_remove_stackable_item(self):
        """スタック可能アイテムを削除できること"""
        slots = InventorySlots.create_empty(5)
        item = ItemQuantity(item=create_test_consumable_item(1, "Test Item"), quantity=10)

        slots = slots.with_item_added(item)
        removed_item, new_slots = slots.with_item_removed(item_id=1, quantity=5)

        assert removed_item.quantity == 5
        assert new_slots.get_total_quantity_by_item_id(1) == 5

    def test_remove_unique_item(self):
        """ユニークアイテムを削除できること"""
        slots = InventorySlots.create_empty(5)
        item = create_test_unique_item(100, 1, "Test Unique")

        slots = slots.with_item_added(item)
        removed_item, new_slots = slots.with_item_removed(unique_id=100)

        assert removed_item.unique_id == 100
        assert not new_slots.has_unique(100)

    def test_has_stackable_item(self):
        """スタック可能アイテムの存在確認が正しく動作すること"""
        slots = InventorySlots.create_empty(5)
        item = ItemQuantity(item=create_test_consumable_item(1, "Test Item"), quantity=10)

        slots = slots.with_item_added(item)

        assert slots.has_stackable(1, 5)  # 5個以上ある
        assert not slots.has_stackable(1, 15)  # 15個はない
        assert not slots.has_stackable(2, 1)  # 別のアイテムはない

    def test_has_unique_item(self):
        """ユニークアイテムの存在確認が正しく動作すること"""
        slots = InventorySlots.create_empty(5)
        item = create_test_unique_item(100, 1, "Test Unique")

        slots = slots.with_item_added(item)

        assert slots.has_unique(100)
        assert not slots.has_unique(200)
