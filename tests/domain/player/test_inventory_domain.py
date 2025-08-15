import pytest

from domain.item.enum import ItemType, Rarity
from domain.item.item import Item
from domain.item.unique_item import UniqueItem
from domain.player.inventory import Inventory


def make_item(item_id: int, name: str = "Item", price: int = 10) -> Item:
    return Item(
        item_id=item_id,
        name=name,
        description=f"desc-{name}",
        price=price,
        type=ItemType.OTHER,
        rarity=Rarity.COMMON,
    )


@pytest.mark.unit
class TestInventoryStackable:
    def test_add_and_remove_stackable(self):
        inv = Inventory()
        potion = make_item(1, name="Potion")
        inv.add_stackable(potion, count=3)
        assert inv.get_stackable_count(1) == 3
        assert inv.get_stackable(1) == potion

        removed = inv.remove_stackable(1, count=2)
        assert removed == 2
        assert inv.get_stackable_count(1) == 1

        removed = inv.remove_stackable(1, count=5)
        assert removed == 1
        assert inv.get_stackable_count(1) == 0
        assert inv.get_stackable(1) is None

    def test_has_stackable_at_least(self):
        inv = Inventory()
        herb = make_item(2, name="Herb")
        inv.add_stackable(herb, count=2)
        assert inv.has_stackable(2, at_least=1) is True
        assert inv.has_stackable(2, at_least=2) is True
        assert inv.has_stackable(2, at_least=3) is False


@pytest.mark.unit
class TestInventoryUnique:
    def test_add_get_remove_unique(self):
        inv = Inventory()
        sword_item = make_item(10, name="Sword")
        u1 = UniqueItem(id=100, item=sword_item, durability=5, attack=3, speed=1)
        inv.add_unique(u1)
        assert inv.get_unique(100) is u1
        assert inv.has_unique_by_item_id(10) is True
        assert inv.list_uniques_by_item_id(10) == [u1]

        removed = inv.remove_unique(100)
        assert removed is True
        assert inv.get_unique(100) is None
        assert inv.has_unique_by_item_id(10) is False

    def test_total_count_and_empty(self):
        inv = Inventory()
        assert inv.is_empty() is True
        inv.add_stackable(make_item(1), count=2)
        inv.add_unique(UniqueItem(id=200, item=make_item(2, name="Armor"), durability=1, defense=1))
        assert inv.get_total_item_count() == 3
        assert inv.is_empty() is False


