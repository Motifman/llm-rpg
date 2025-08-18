import pytest
from src.domain.player.player import Player
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.player_enum import Role
from src.domain.item.item import Item
from src.domain.item.item_enum import ItemType, Rarity
from src.domain.item.item_effect import ItemEffect
from src.domain.battle.status_effect import StatusEffect
from src.domain.battle.battle_enum import StatusEffectType, Element
from src.domain.conversation.message_box import MessageBox
from src.domain.monster.monster_enum import Race


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
        dynamic_status = DynamicStatus(
            hp=80,
            max_hp=100,
            mp=30,
            max_mp=50,
            exp=100,
            level=5,
            gold=500
        )
        inventory = Inventory()
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
    
    def create_consumable_item(self, item_id: int, name: str, effect: ItemEffect) -> Item:
        """消費アイテムを作成"""
        return Item(
            item_id=item_id,
            name=name,
            description=f"{name}の説明",
            price=100,
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            item_effect=effect
        )
    
    def test_use_item_hp_recovery(self):
        """HP回復アイテムの使用テスト"""
        # HP回復効果を持つアイテムを作成
        effect = ItemEffect(hp_delta=20)
        potion = self.create_consumable_item(1, "ヒールポーション", effect)
        
        # アイテムをインベントリに追加
        self.player.add_item(potion, 2)
        
        # 初期HP確認
        initial_hp = self.player.hp
        assert initial_hp == 80
        
        # アイテムを使用
        self.player.use_item(potion)
        
        # HP回復を確認
        assert self.player.hp == initial_hp + 20
        # アイテムが消費されたことを確認
        assert self.player.has_stackable_item(1, 1)
        assert not self.player.has_stackable_item(1, 2)
    
    def test_use_item_mp_recovery(self):
        """MP回復アイテムの使用テスト"""
        # MP回復効果を持つアイテムを作成
        effect = ItemEffect(mp_delta=15)
        ether = self.create_consumable_item(2, "エーテル", effect)
        
        # アイテムをインベントリに追加
        self.player.add_item(ether, 1)
        
        # 初期MP確認
        initial_mp = self.player.mp
        assert initial_mp == 30
        
        # アイテムを使用
        self.player.use_item(ether)
        
        # MP回復を確認
        assert self.player.mp == initial_mp + 15
        # アイテムが消費されたことを確認
        assert not self.player.has_stackable_item(2)
    
    def test_use_item_gold_gain(self):
        """所持金増加アイテムの使用テスト"""
        # 所持金増加効果を持つアイテムを作成
        effect = ItemEffect(gold_delta=250)
        gold_coin = self.create_consumable_item(3, "金貨袋", effect)
        
        # アイテムをインベントリに追加
        self.player.add_item(gold_coin, 1)
        
        # 初期所持金確認
        initial_gold = self.player.gold
        assert initial_gold == 500
        
        # アイテムを使用
        self.player.use_item(gold_coin)
        
        # 所持金増加を確認
        assert self.player.gold == initial_gold + 250
        # アイテムが消費されたことを確認
        assert not self.player.has_stackable_item(3)
    
    def test_use_item_exp_gain(self):
        """経験値増加アイテムの使用テスト"""
        # 経験値増加効果を持つアイテムを作成
        effect = ItemEffect(exp_delta=50)
        exp_book = self.create_consumable_item(4, "経験の書", effect)
        
        # アイテムをインベントリに追加
        self.player.add_item(exp_book, 1)
        
        # 初期経験値確認
        initial_exp = self.player.exp
        assert initial_exp == 100
        
        # アイテムを使用
        self.player.use_item(exp_book)
        
        # 経験値増加を確認
        assert self.player.exp == initial_exp + 50
        # アイテムが消費されたことを確認
        assert not self.player.has_stackable_item(4)
    
    def test_use_item_multiple_effects(self):
        """複数の効果を持つアイテムの使用テスト"""
        # HP回復 + 経験値増加の効果を持つアイテムを作成
        effect = ItemEffect(
            hp_delta=15,  # 30から15に変更（80 + 15 = 95なので最大値内）
            exp_delta=25
        )
        super_potion = self.create_consumable_item(6, "万能薬", effect)
        
        # アイテムをインベントリに追加
        self.player.add_item(super_potion, 1)
        
        # 初期値確認
        initial_hp = self.player.hp
        initial_exp = self.player.exp
        
        # アイテムを使用
        self.player.use_item(super_potion)
        
        # 全ての効果を確認
        assert self.player.hp == initial_hp + 15
        assert self.player.exp == initial_exp + 25
        # アイテムが消費されたことを確認
        assert not self.player.has_stackable_item(6)
    
    def test_use_item_multiple_count(self):
        """複数個のアイテムを一度に使用するテスト"""
        # HP回復効果を持つアイテムを作成
        effect = ItemEffect(hp_delta=5)  # 10から5に変更（5 * 3 = 15なので、80 + 15 = 95で最大値内）
        small_potion = self.create_consumable_item(7, "小さなポーション", effect)
        
        # アイテムをインベントリに追加
        self.player.add_item(small_potion, 5)
        
        # 初期HP確認
        initial_hp = self.player.hp
        
        # アイテムを3個使用
        self.player.use_item(small_potion, 3)
        
        # HP回復を確認（5 * 3 = 15）
        assert self.player.hp == initial_hp + 15
        # 残りアイテム数を確認
        assert self.player.has_stackable_item(7, 2)
        assert not self.player.has_stackable_item(7, 3)
    
    def test_use_item_not_enough_items(self):
        """十分な数のアイテムを持っていない場合のテスト"""
        # HP回復効果を持つアイテムを作成
        effect = ItemEffect(hp_delta=20)
        potion = self.create_consumable_item(8, "ポーション", effect)
        
        # アイテムを1個だけインベントリに追加
        self.player.add_item(potion, 1)
        
        # 2個使用しようとしてエラーが発生することを確認
        with pytest.raises(AssertionError, match="Player does not have enough ポーション"):
            self.player.use_item(potion, 2)
        
        # アイテムが消費されていないことを確認
        assert self.player.has_stackable_item(8, 1)
    
    def test_use_item_not_in_inventory(self):
        """インベントリにないアイテムを使用しようとした場合のテスト"""
        # HP回復効果を持つアイテムを作成
        effect = ItemEffect(hp_delta=20)
        potion = self.create_consumable_item(9, "存在しないポーション", effect)
        
        # インベントリにアイテムを追加しない
        
        # 存在しないアイテムを使用しようとしてエラーが発生することを確認
        with pytest.raises(AssertionError, match="Player does not have enough 存在しないポーション"):
            self.player.use_item(potion)
    
    def test_use_item_not_consumable(self):
        """消費アイテムでないアイテムを使用しようとした場合のテスト"""
        # 消費アイテムでないアイテムを作成
        equipment_item = Item(
            item_id=10,
            name="剣",
            description="普通の剣",
            price=500,
            item_type=ItemType.WEAPON,  # 消費アイテムではない
            rarity=Rarity.COMMON
        )
        
        # アイテムをインベントリに追加
        self.player.add_item(equipment_item, 1)
        
        # 消費アイテムでないアイテムを使用しようとしてエラーが発生することを確認
        with pytest.raises(AssertionError, match="Item type must be CONSUMABLE"):
            self.player.use_item(equipment_item)
        
        # アイテムが消費されていないことを確認
        assert self.player.has_stackable_item(10, 1)
    
    def test_use_item_no_effect(self):
        """効果のないアイテムの使用テスト"""
        # 効果のないアイテムを作成
        no_effect_item = Item(
            item_id=11,
            name="何もしないアイテム",
            description="何の効果もない",
            price=1,
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            item_effect=None
        )
        
        # アイテムをインベントリに追加
        self.player.add_item(no_effect_item, 1)
        
        # 初期状態を記録
        initial_hp = self.player.hp
        initial_mp = self.player.mp
        initial_gold = self.player.gold
        initial_exp = self.player.exp
        
        # アイテムを使用
        self.player.use_item(no_effect_item)
        
        # 何も変化しないことを確認
        assert self.player.hp == initial_hp
        assert self.player.mp == initial_mp
        assert self.player.gold == initial_gold
        assert self.player.exp == initial_exp
        # アイテムが消費されたことを確認
        assert not self.player.has_stackable_item(11)
    
    def test_use_item_hp_over_max(self):
        """最大HPを超える回復アイテムの使用テスト"""
        # 大量HP回復効果を持つアイテムを作成
        effect = ItemEffect(hp_delta=50)
        mega_potion = self.create_consumable_item(12, "メガポーション", effect)
        
        # アイテムをインベントリに追加
        self.player.add_item(mega_potion, 1)
        
        # 現在のHP/最大HPを確認
        assert self.player.hp == 80
        assert self.player.max_hp == 100
        
        # アイテムを使用
        self.player.use_item(mega_potion)
        
        # HPが最大値でキャップされることを確認
        assert self.player.hp == 100  # 80 + 50 = 130だが、最大値100でキャップ
        # アイテムが消費されたことを確認
        assert not self.player.has_stackable_item(12)
