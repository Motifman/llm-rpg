import pytest

from src.domain.item.item_enum import ItemType, Rarity
from src.domain.item.item import Item
from src.domain.item.unique_item import UniqueItem
from src.domain.item.consumable_item import ConsumableItem
from src.domain.item.equipment_item import EquipmentItem
from src.domain.item.item_quantity import ItemQuantity
from src.domain.item.durability import Durability
from src.domain.item.item_effect import ItemEffect
from src.domain.player.base_status import BaseStatus


@pytest.mark.unit
class TestItem:
    def test_item_basic_constraints(self):
        item = Item(
            item_id=1,
            name="Iron Sword",
            description="A basic iron sword",
            item_type=ItemType.WEAPON,
            rarity=Rarity.COMMON,
        )
        assert item.is_tradeable

        with pytest.raises(ValueError):
            Item(item_id=-1, name="n", description="d", item_type=ItemType.OTHER, rarity=Rarity.COMMON)
        with pytest.raises(ValueError):
            Item(item_id=1, name="", description="d", item_type=ItemType.OTHER, rarity=Rarity.COMMON)
        with pytest.raises(ValueError):
            Item(item_id=1, name="n", description="", item_type=ItemType.OTHER, rarity=Rarity.COMMON)


@pytest.mark.unit
class TestUniqueItem:
    def test_unique_item_constraints_and_behavior(self):
        unique = UniqueItem(
            unique_id=10,
            item_id=2,
            name="Leather Armor",
            description="Simple armor",
            item_type=ItemType.CHEST,
            rarity=Rarity.UNCOMMON,
        )
        assert unique.is_tradeable is True
        assert unique.unique_id == 10
        
        with pytest.raises(ValueError):
            UniqueItem(unique_id=-1, item_id=1, name="test", description="test", item_type=ItemType.OTHER, rarity=Rarity.COMMON)

    def test_unique_item_equality(self):
        unique1 = UniqueItem(
            unique_id=1,
            item_id=1,
            name="Sword",
            description="A sword",
            item_type=ItemType.WEAPON,
            rarity=Rarity.COMMON,
        )
        unique2 = UniqueItem(
            unique_id=1,
            item_id=2,  # 異なるitem_idでも
            name="Different",  # 異なる名前でも
            description="Different",
            item_type=ItemType.HELMET,
            rarity=Rarity.RARE,
        )
        unique3 = UniqueItem(
            unique_id=2,
            item_id=1,
            name="Sword",
            description="A sword",
            item_type=ItemType.WEAPON,
            rarity=Rarity.COMMON,
        )
        
        # unique_idが同じなら等しい
        assert unique1 == unique2
        # unique_idが異なれば等しくない
        assert unique1 != unique3
        
        # ハッシュ値も確認
        assert hash(unique1) == hash(unique2)
        assert hash(unique1) != hash(unique3)


@pytest.mark.unit
class TestConsumableItem:
    def test_consumable_item_creation(self):
        from src.domain.item.item_effect import HealEffect
        effect = HealEffect(50)
        consumable = ConsumableItem(
            item_id=1,
            name="Health Potion",
            description="Restores HP",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            effect=effect
        )
        assert consumable.effect == effect
        assert consumable.is_tradeable is True


@pytest.mark.unit
class TestEquipmentItem:
    def test_equipment_item_creation(self):
        base_status = BaseStatus(attack=10, defense=5, speed=2, critical_rate=0.05, evasion_rate=0.02)
        durability = Durability(100, 100)
        
        equipment = EquipmentItem(
            item_id=1,
            name="Iron Sword",
            description="A basic sword",
            item_type=ItemType.WEAPON,
            rarity=Rarity.COMMON,
            unique_id=1,
            base_status=base_status,
            durability=durability
        )
        
        assert equipment.base_status == base_status
        assert equipment.durability == durability
        assert not equipment.is_broken()
        assert equipment.is_tradeable is True

    def test_equipment_item_broken_validation(self):
        base_status = BaseStatus(attack=10, defense=5, speed=2, critical_rate=0.05, evasion_rate=0.02)
        broken_durability = Durability(0, 100)
        
        with pytest.raises(ValueError):
            EquipmentItem(
                item_id=1,
                name="Broken Sword",
                description="A broken sword",
                item_type=ItemType.WEAPON,
                rarity=Rarity.COMMON,
                unique_id=1,
                base_status=base_status,
                durability=broken_durability
            )


@pytest.mark.unit
class TestItemQuantity:
    def test_item_quantity_creation(self):
        item = Item(
            item_id=1,
            name="Potion",
            description="A healing potion",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON
        )
        quantity = ItemQuantity(item, 5)
        
        assert quantity.item == item
        assert quantity.quantity == 5

    def test_item_quantity_validation(self):
        item = Item(
            item_id=1,
            name="Potion",
            description="A healing potion",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON
        )
        
        # 負の数量はエラー
        with pytest.raises(ValueError):
            ItemQuantity(item, -1)
        
        # UniqueItemは数量を持てない
        unique_item = UniqueItem(
            unique_id=1,
            item_id=1,
            name="Unique Sword",
            description="A unique sword",
            item_type=ItemType.WEAPON,
            rarity=Rarity.RARE
        )
        with pytest.raises(ValueError):
            ItemQuantity(unique_item, 1)

    def test_item_quantity_split(self):
        item = Item(
            item_id=1,
            name="Potion",
            description="A healing potion",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON
        )
        quantity = ItemQuantity(item, 10)
        
        # 3個分割
        part1, part2 = quantity.split(3)
        
        assert part1.quantity == 3
        assert part2.quantity == 7
        assert part1.item == item
        assert part2.item == item

    def test_item_quantity_split_validation(self):
        item = Item(
            item_id=1,
            name="Potion",
            description="A healing potion",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON
        )
        quantity = ItemQuantity(item, 5)
        
        # 無効な分割量
        with pytest.raises(ValueError):
            quantity.split(0)  # 0以下
        with pytest.raises(ValueError):
            quantity.split(5)  # 全体以上
        with pytest.raises(ValueError):
            quantity.split(6)  # 全体超過

    def test_item_quantity_merge(self):
        item = Item(
            item_id=1,
            name="Potion",
            description="A healing potion",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON
        )
        quantity1 = ItemQuantity(item, 3)
        quantity2 = ItemQuantity(item, 7)
        
        merged = quantity1.merge(quantity2)
        
        assert merged.quantity == 10
        assert merged.item == item

    def test_item_quantity_merge_validation(self):
        item1 = Item(
            item_id=1,
            name="Potion",
            description="A healing potion",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON
        )
        item2 = Item(
            item_id=2,
            name="Herb",
            description="A healing herb",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON
        )
        
        quantity1 = ItemQuantity(item1, 3)
        quantity2 = ItemQuantity(item2, 7)
        
        # 異なるアイテムはマージできない
        with pytest.raises(ValueError):
            quantity1.merge(quantity2)


@pytest.mark.unit
class TestDurability:
    def test_durability_creation(self):
        durability = Durability(80, 100)
        assert durability.durability == 80
        assert durability.max_durability == 100
        assert not durability.is_broken()

    def test_durability_validation(self):
        # 現在値が最大値を超える場合
        with pytest.raises(ValueError):
            Durability(120, 100)
        
        # 負の値
        with pytest.raises(ValueError):
            Durability(-1, 100)

    def test_durability_damage(self):
        durability = Durability(80, 100)
        
        # 20ダメージ
        result = durability.damage(20)
        assert result.durability == 60
        assert durability.durability == 80  # 元のインスタンスは変更されない
        
        # オーバーダメージ
        result = durability.damage(100)
        assert result.durability == 0
        assert result.is_broken()

    def test_durability_repair(self):
        durability = Durability(50, 100)
        
        # 30修理
        result = durability.repair(30)
        assert result.durability == 80
        assert durability.durability == 50  # 元のインスタンスは変更されない
        
        # オーバー修理
        result = durability.repair(50)
        assert result.durability == 100