import pytest

from domain.item.item_enum import ItemType, Rarity
from domain.item.item import Item
from domain.item.unique_item import UniqueItem


@pytest.mark.unit
class TestItemCatalog:
    def test_item_basic_constraints(self):
        item = Item(
            item_id=1,
            name="Iron Sword",
            description="A basic iron sword",
            price=100,
            type=ItemType.WEAPON,
            rarity=Rarity.COMMON,
        )
        assert item.can_be_traded() is True

        with pytest.raises(AssertionError):
            Item(item_id=-1, name="n", description="d", price=0, type=ItemType.OTHER, rarity=Rarity.COMMON)
        with pytest.raises(AssertionError):
            Item(item_id=1, name="", description="d", price=0, type=ItemType.OTHER, rarity=Rarity.COMMON)
        with pytest.raises(AssertionError):
            Item(item_id=1, name="n", description="", price=0, type=ItemType.OTHER, rarity=Rarity.COMMON)
        with pytest.raises(AssertionError):
            Item(item_id=1, name="n", description="d", price=-1, type=ItemType.OTHER, rarity=Rarity.COMMON)


@pytest.mark.unit
class TestUniqueItem:
    def test_unique_item_constraints_and_behavior(self):
        base = Item(
            item_id=2,
            name="Leather Armor",
            description="Simple armor",
            price=80,
            type=ItemType.CHEST,
            rarity=Rarity.UNCOMMON,
        )
        unique = UniqueItem(id=10, item=base, durability=5, defense=2, speed=1)
        assert unique.can_be_traded() is True
        assert unique.is_broken() is False

        broken = unique.use_durability(amount=3)
        assert broken is False
        assert unique.durability == 2
        broken = unique.use_durability(amount=3)
        assert broken is True
        assert unique.is_broken() is True
        assert unique.can_be_traded() is False

        with pytest.raises(AssertionError):
            UniqueItem(id=-1, item=base, durability=0)
        with pytest.raises(AssertionError):
            UniqueItem(id=1, item=base, durability=-1)
        with pytest.raises(AssertionError):
            UniqueItem(id=1, item=base, durability=0, attack=-1)
        with pytest.raises(AssertionError):
            UniqueItem(id=1, item=base, durability=0, defense=-1)
        with pytest.raises(AssertionError):
            UniqueItem(id=1, item=base, durability=0, speed=-1)


