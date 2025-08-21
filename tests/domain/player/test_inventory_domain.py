import pytest

from src.domain.item.item_enum import ItemType, Rarity
from src.domain.item.item import Item
from src.domain.item.unique_item import UniqueItem
from src.domain.item.item_quantity import ItemQuantity
from src.domain.player.inventory import Inventory, InventorySlot


def make_item(item_id: int, name: str = "Item") -> Item:
    return Item(
        item_id=item_id,
        name=name,
        description=f"desc-{name}",
        item_type=ItemType.OTHER,
        rarity=Rarity.COMMON,
    )


def make_unique_item(unique_id: int, item_id: int, name: str = "UniqueItem") -> UniqueItem:
    return UniqueItem(
        unique_id=unique_id,
        item_id=item_id,
        name=name,
        description=f"desc-{name}",
        item_type=ItemType.WEAPON,
        rarity=Rarity.COMMON,
    )


@pytest.mark.unit
class TestInventorySlot:
    def test_empty_slot(self):
        slot = InventorySlot.create_empty(0)
        assert slot.is_empty()
        assert not slot.is_stackable()
        assert not slot.is_unique()

    def test_add_stackable_item(self):
        slot = InventorySlot.create_empty(0)
        item = make_item(1, "Potion")
        item_quantity = ItemQuantity(item, 3)
        
        assert slot.can_stack_with(item_quantity)
        slot.add_stackable(item_quantity)
        
        assert not slot.is_empty()
        assert slot.is_stackable()
        assert slot.content.quantity == 3

    def test_add_unique_item(self):
        slot = InventorySlot.create_empty(0)
        unique_item = make_unique_item(1, 10, "Sword")
        
        slot.add_unique(unique_item)
        
        assert not slot.is_empty()
        assert slot.is_unique()
        assert slot.content == unique_item

    def test_stack_items(self):
        slot = InventorySlot.create_empty(0)
        item = make_item(1, "Potion")
        
        # 最初に3個追加
        item_quantity1 = ItemQuantity(item, 3)
        slot.add_stackable(item_quantity1)
        
        # さらに2個追加
        item_quantity2 = ItemQuantity(item, 2)
        assert slot.can_stack_with(item_quantity2)
        slot.add_stackable(item_quantity2)
        
        assert slot.content.quantity == 5

    def test_cannot_stack_different_items(self):
        slot = InventorySlot.create_empty(0)
        item1 = make_item(1, "Potion")
        item2 = make_item(2, "Herb")
        
        slot.add_stackable(ItemQuantity(item1, 3))
        
        assert not slot.can_stack_with(ItemQuantity(item2, 2))

    def test_remove_stackable(self):
        slot = InventorySlot.create_empty(0)
        item = make_item(1, "Potion")
        slot.add_stackable(ItemQuantity(item, 5))
        
        # 2個削除
        removed = slot.remove_stackable(1, 2)
        assert removed.quantity == 2
        assert slot.content.quantity == 3
        
        # 全部削除
        removed = slot.remove_stackable(1, 3)
        assert removed.quantity == 3
        assert slot.is_empty()

    def test_remove_unique(self):
        slot = InventorySlot.create_empty(0)
        unique_item = make_unique_item(1, 10, "Sword")
        slot.add_unique(unique_item)
        
        removed = slot.remove_unique(1)
        assert removed == unique_item
        assert slot.is_empty()


@pytest.mark.unit
class TestInventory:
    def test_create_empty_inventory(self):
        inv = Inventory.create_empty(10)
        assert len(inv.slots) == 10
        assert inv.max_slots == 10
        
        for i in range(10):
            assert inv.get_slot_by_id(i) is not None
            assert inv.get_slot_by_id(i).is_empty()

    def test_add_stackable_item(self):
        inv = Inventory.create_empty(5)
        item = make_item(1, "Potion")
        item_quantity = ItemQuantity(item, 3)
        
        result = inv.add_item(item_quantity)
        assert result is True
        
        # 数量を確認
        assert inv.get_total_quantity_by_item_id(1) == 3
        assert inv.has_stackable(1, 3)
        assert not inv.has_stackable(1, 4)

    def test_add_unique_item(self):
        inv = Inventory.create_empty(5)
        unique_item = make_unique_item(1, 10, "Sword")
        
        result = inv.add_item(unique_item)
        assert result is True
        
        # アイテムを確認
        assert inv.has_unique(1)
        retrieved = inv.get_item_by_unique_id(1)
        assert retrieved == unique_item

    def test_stack_same_items(self):
        inv = Inventory.create_empty(5)
        item = make_item(1, "Potion")
        
        # 最初に3個追加
        inv.add_item(ItemQuantity(item, 3))
        # さらに2個追加（同じスロットにスタック）
        inv.add_item(ItemQuantity(item, 2))
        
        assert inv.get_total_quantity_by_item_id(1) == 5
        # スロットは1つだけ使用されている
        used_slots = [slot for slot in inv.slots if not slot.is_empty()]
        assert len(used_slots) == 1

    def test_remove_stackable_item(self):
        inv = Inventory.create_empty(5)
        item = make_item(1, "Potion")
        inv.add_item(ItemQuantity(item, 5))
        
        # 2個削除
        removed = inv.remove_item(item_id=1, quantity=2)
        assert removed.quantity == 2
        assert inv.get_total_quantity_by_item_id(1) == 3

    def test_remove_unique_item(self):
        inv = Inventory.create_empty(5)
        unique_item = make_unique_item(1, 10, "Sword")
        inv.add_item(unique_item)
        
        removed = inv.remove_item(unique_id=1)
        assert removed == unique_item
        assert not inv.has_unique(1)

    def test_search_item_by_id(self):
        inv = Inventory.create_empty(5)
        item = make_item(1, "Potion")
        inv.add_item(ItemQuantity(item, 3))
        
        found = inv.search_item(item_id=1)
        assert found is not None
        assert found.quantity == 3

    def test_search_item_by_unique_id(self):
        inv = Inventory.create_empty(5)
        unique_item = make_unique_item(1, 10, "Sword")
        inv.add_item(unique_item)
        
        found = inv.search_item(unique_id=1)
        assert found == unique_item

    def test_search_item_by_slot_id(self):
        inv = Inventory.create_empty(5)
        item = make_item(1, "Potion")
        inv.add_item(ItemQuantity(item, 3))
        
        found = inv.search_item(slot_id=0)
        assert found is not None
        assert found.quantity == 3

    def test_inventory_full_stackable(self):
        inv = Inventory.create_empty(2)  # 2スロットのみ
        item1 = make_item(1, "Potion")
        item2 = make_item(2, "Herb")
        item3 = make_item(3, "Elixir")
        
        # 2つのスロットを埋める
        assert inv.add_item(ItemQuantity(item1, 1))
        assert inv.add_item(ItemQuantity(item2, 1))
        
        # 3つ目は失敗
        assert not inv.add_item(ItemQuantity(item3, 1))

    def test_inventory_full_unique(self):
        inv = Inventory.create_empty(2)  # 2スロットのみ
        unique1 = make_unique_item(1, 10, "Sword")
        unique2 = make_unique_item(2, 11, "Shield")
        unique3 = make_unique_item(3, 12, "Axe")
        
        # 2つのスロットを埋める
        assert inv.add_item(unique1)
        assert inv.add_item(unique2)
        
        # 3つ目は失敗
        assert not inv.add_item(unique3)

    def test_index_consistency(self):
        inv = Inventory.create_empty(10)
        item = make_item(1, "Potion")
        unique_item = make_unique_item(1, 10, "Sword")
        
        # アイテム追加
        inv.add_item(ItemQuantity(item, 3))
        inv.add_item(unique_item)
        
        # インデックス確認
        assert 1 in inv._item_id_index
        assert 1 in inv._unique_id_index
        
        # アイテム削除
        inv.remove_item(item_id=1, quantity=3)
        inv.remove_item(unique_id=1)
        
        # インデックス削除確認
        assert 1 not in inv._item_id_index
        assert 1 not in inv._unique_id_index

    def test_get_slots_by_item_id(self):
        inv = Inventory.create_empty(10)
        item = make_item(1, "Potion")
        
        # 複数のスロットに同じアイテムを分散させる
        # （通常は同じスロットにスタックされるが、テスト用に強制的に分散）
        inv.slots[0].add_stackable(ItemQuantity(item, 50))
        inv.slots[1].add_stackable(ItemQuantity(item, 30))
        inv._rebuild_indexes()
        
        slots = inv.get_slots_by_item_id(1)
        assert len(slots) == 2
        
        total_quantity = sum(slot.content.quantity for slot in slots)
        assert total_quantity == 80