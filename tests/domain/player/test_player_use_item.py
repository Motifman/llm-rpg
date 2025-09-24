import pytest
from src.domain.player.player import Player
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.player_enum import Role
from src.domain.item.item import Item
from src.domain.item.consumable_item import ConsumableItem
from src.domain.item.item_quantity import ItemQuantity
from src.domain.item.item_enum import ItemType, Rarity
from src.domain.item.item_effect import HealEffect, RecoverMpEffect
from src.domain.player.message_box import MessageBox
from src.domain.monster.monster_enum import Race
from src.domain.battle.battle_enum import Element
from src.domain.trade.trade_exception import InsufficientItemsException
from src.domain.item.item_exception import ItemNotUsableException
from src.domain.common.value_object import Exp, Gold


class TestPlayerUseItem:
    """Playerのuse_itemメソッドのテスト"""
    
    def setup_method(self):
        """テスト用のプレイヤーを作成"""
        base_status = BaseStatus(
            attack=10,
            defense=8,
            speed=6,
            critical_rate=0.1,
            evasion_rate=0.05
        )
        dynamic_status = DynamicStatus.new_game(max_hp=100, max_mp=50, max_exp=1000, initial_level=5)
        # 初期値を調整
        dynamic_status.take_damage(20)  # HP 100 -> 80
        dynamic_status.consume_mp(20)  # MP 50 -> 30
        dynamic_status.receive_exp(Exp(100, 1000))
        dynamic_status.receive_gold(Gold(500))
        inventory = Inventory.create_empty(20)
        equipment_set = EquipmentSet()
        message_box = MessageBox()
        
        self.player = Player(
            player_id=1,
            name="テストプレイヤー",
            role=Role.ADVENTURER,
            current_spot_id=1,
            base_status=base_status,
            dynamic_status=dynamic_status,
            inventory=inventory,
            equipment_set=equipment_set,
            message_box=message_box,
            race=Race.HUMAN,
            element=Element.NEUTRAL
        )
    
    def create_consumable_item(self, item_id: int, name: str, effect) -> ConsumableItem:
        """消費アイテムを作成"""
        return ConsumableItem(
            item_id=item_id,
            name=name,
            description=f"{name}の説明",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            effect=effect
        )
    
    def test_use_item_hp_recovery(self):
        """HP回復アイテムの使用テスト"""
        # HP回復効果を持つアイテムを作成
        effect = HealEffect(amount=20)
        potion = self.create_consumable_item(1, "ヒールポーション", effect)
        
        # アイテムをインベントリに追加
        item_quantity = ItemQuantity(potion, 2)
        self.player._inventory.add_item(item_quantity)
        
        # 初期HP確認
        initial_hp = self.player._dynamic_status._hp.value
        assert initial_hp == 80
        
        # アイテムを使用
        self.player.use_item(1, 1)
        
        # HP回復を確認
        assert self.player._dynamic_status._hp.value == initial_hp + 20
        # アイテムが消費されたことを確認
        assert self.player._inventory.has_stackable(1, 1)
        assert not self.player._inventory.has_stackable(1, 2)
    
    def test_use_item_mp_recovery(self):
        """MP回復アイテムの使用テスト"""
        # MP回復効果を持つアイテムを作成
        effect = RecoverMpEffect(amount=15)
        ether = self.create_consumable_item(2, "エーテル", effect)
        
        # アイテムをインベントリに追加
        item_quantity = ItemQuantity(ether, 1)
        self.player._inventory.add_item(item_quantity)
        
        # 初期MP確認
        initial_mp = self.player._dynamic_status._mp.value
        assert initial_mp == 30
        
        # アイテムを使用
        self.player.use_item(2, 1)
        
        # MP回復を確認
        assert self.player._dynamic_status._mp.value == initial_mp + 15
        # アイテムが消費されたことを確認
        assert not self.player._inventory.has_stackable(2, 1)
    
    def test_use_item_multiple_count(self):
        """複数個のアイテムを一度に使用するテスト"""
        # HP回復効果を持つアイテムを作成
        effect = HealEffect(amount=5)
        small_potion = self.create_consumable_item(3, "小さなポーション", effect)
        
        # アイテムをインベントリに追加
        item_quantity = ItemQuantity(small_potion, 5)
        self.player._inventory.add_item(item_quantity)
        
        # 初期HP確認（他のテストの影響でHPが変わっている可能性がある）
        initial_hp = self.player._dynamic_status._hp.value
        
        # アイテムを3個使用
        self.player.use_item(3, 3)
        
        # HP回復を確認（5 * 3 = 15、ただし最大HPでキャップされる）
        expected_hp = min(initial_hp + 15, self.player._dynamic_status._hp.max_hp)
        assert self.player._dynamic_status._hp.value == expected_hp
        # 残りアイテム数を確認
        assert self.player._inventory.has_stackable(3, 2)
        assert not self.player._inventory.has_stackable(3, 3)
    
    def test_use_item_not_enough_items(self):
        """十分な数のアイテムを持っていない場合のテスト"""
        # HP回復効果を持つアイテムを作成
        effect = HealEffect(amount=20)
        potion = self.create_consumable_item(4, "ポーション", effect)
        
        # アイテムを1個だけインベントリに追加
        item_quantity = ItemQuantity(potion, 1)
        self.player._inventory.add_item(item_quantity)
        
        # 2個使用しようとしてエラーが発生することを確認
        with pytest.raises(InsufficientItemsException):
            self.player.use_item(4, 2)
        
        # アイテムが消費されていないことを確認
        assert self.player._inventory.has_stackable(4, 1)
    
    def test_use_item_not_in_inventory(self):
        """インベントリにないアイテムを使用しようとした場合のテスト"""
        # 存在しないアイテムを使用しようとしてエラーが発生することを確認
        with pytest.raises(InsufficientItemsException):
            self.player.use_item(999, 1)
    
    def test_use_item_not_consumable(self):
        """消費アイテムでないアイテムを使用しようとした場合のテスト"""
        # 消費アイテムでないアイテムを作成
        equipment_item = Item(
            item_id=10,
            name="剣",
            description="普通の剣",
            item_type=ItemType.WEAPON,
            rarity=Rarity.COMMON
        )
        
        # アイテムをインベントリに追加
        item_quantity = ItemQuantity(equipment_item, 1)
        self.player._inventory.add_item(item_quantity)
        
        # 消費アイテムでないアイテムを使用しようとしてエラーが発生することを確認
        with pytest.raises(ItemNotUsableException):
            self.player.use_item(10, 1)
        
        # アイテムが消費されていないことを確認
        assert self.player._inventory.has_stackable(10, 1)
    
    def test_use_item_hp_over_max(self):
        """最大HPを超える回復アイテムの使用テスト"""
        # 大量HP回復効果を持つアイテムを作成
        effect = HealEffect(amount=50)
        mega_potion = self.create_consumable_item(5, "メガポーション", effect)
        
        # アイテムをインベントリに追加
        item_quantity = ItemQuantity(mega_potion, 1)
        self.player._inventory.add_item(item_quantity)
        
        # 現在のHP/最大HPを確認
        assert self.player._dynamic_status._hp.value == 80
        assert self.player._dynamic_status._hp.max_hp == 100
        
        # アイテムを使用
        self.player.use_item(5, 1)
        
        # HPが最大値でキャップされることを確認
        assert self.player._dynamic_status._hp.value == 100
        # アイテムが消費されたことを確認
        assert not self.player._inventory.has_stackable(5, 1)