import pytest
from src.domain.item.item import Item
from src.domain.item.unique_item import UniqueItem
from src.domain.item.item_enum import ItemType, Rarity
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.conversation.message_box import MessageBox
from src.domain.player.player_enum import Role
from src.domain.battle.battle_enum import StatusEffectType
from src.domain.player.player import Player


class TestPlayerEquipmentIntegration:
    """プレイヤーと装備システムの統合テスト"""
    
    @pytest.fixture
    def sample_player(self):
        """サンプルプレイヤーを作成"""
        base_status = BaseStatus(attack=10, defense=5, speed=7, critical_rate=0.1, evasion_rate=0.05)
        dynamic_status = DynamicStatus(hp=100, mp=50, max_hp=100, max_mp=50, exp=0, level=1, gold=1000)
        inventory = Inventory()
        equipment_set = EquipmentSet()
        message_box = MessageBox()
        
        return Player(
            player_id=1,
            name="勇者",
            role=Role.ADVENTURER,
            current_spot_id=100,
            base_status=base_status,
            dynamic_status=dynamic_status,
            inventory=inventory,
            equipment_set=equipment_set,
            message_box=message_box
        )
    
    @pytest.fixture
    def sample_equipment_items(self):
        """サンプル装備アイテムを作成"""
        helmet_item = Item(
            item_id=1, name="鉄のヘルメット", description="頑丈なヘルメット",
            price=100, type=ItemType.HELMET, rarity=Rarity.COMMON
        )
        helmet = UniqueItem(id=1, item=helmet_item, durability=100, defense=5)
        
        chest_item = Item(
            item_id=2, name="鉄の胸当て", description="頑丈な胸当て",
            price=200, type=ItemType.CHEST, rarity=Rarity.COMMON
        )
        chest = UniqueItem(id=2, item=chest_item, durability=150, defense=10)
        
        gloves_item = Item(
            item_id=3, name="革手袋", description="器用さを上げる手袋",
            price=50, type=ItemType.GLOVES, rarity=Rarity.COMMON
        )
        gloves = UniqueItem(id=3, item=gloves_item, durability=80, attack=3, speed=2)
        
        shoes_item = Item(
            item_id=4, name="革靴", description="軽快な革靴",
            price=75, type=ItemType.SHOES, rarity=Rarity.COMMON
        )
        shoes = UniqueItem(id=4, item=shoes_item, durability=120, defense=3, speed=1)
        
        return {"helmet": helmet, "chest": chest, "gloves": gloves, "shoes": shoes}

    def test_initial_player_has_empty_equipment(self, sample_player):
        """初期状態でプレイヤーは装備を何も着けていない"""
        assert sample_player.equipment.is_empty()
        assert sample_player.equipment.get_equipped_count() == 0
        assert sample_player.equipment.get_attack_bonus() == 0
        assert sample_player.equipment.get_defense_bonus() == 0
        assert sample_player.equipment.get_speed_bonus() == 0

    def test_equipment_bonus_affects_player_stats(self, sample_player, sample_equipment_items):
        """装備ボーナスがプレイヤーのステータスに反映される"""
        helmet = sample_equipment_items["helmet"]
        gloves = sample_equipment_items["gloves"]
        
        # 装備前のステータス確認（ベース: 攻撃10, 防御5, 素早さ7）
        assert sample_player.attack == 10
        assert sample_player.defense == 5
        assert sample_player.speed == 7
        
        # ヘルメット装備（防御+5）
        sample_player.equipment.equip_helmet(helmet)
        assert sample_player.attack == 10  # 変化なし
        assert sample_player.defense == 10  # 5 + 5
        assert sample_player.speed == 7    # 変化なし
        
        # グローブ追加装備（攻撃+3, 素早さ+2）
        sample_player.equipment.equip_gloves(gloves)
        assert sample_player.attack == 13  # 10 + 3
        assert sample_player.defense == 10 # 5 + 5
        assert sample_player.speed == 9    # 7 + 2

    def test_equip_item_from_inventory(self, sample_player, sample_equipment_items):
        """インベントリからアイテムを装備できる"""
        helmet = sample_equipment_items["helmet"]
        
        # インベントリに追加
        sample_player.add_item(helmet)
        assert sample_player.has_unique_item(helmet.id)
        
        # 装備実行
        success = sample_player.equip_item_from_inventory(helmet.id)
        assert success
        
        # 結果確認
        assert sample_player.equipment.helmet == helmet
        assert not sample_player.has_unique_item(helmet.id)  # インベントリから削除
        assert sample_player.defense == 10  # 防御ボーナス適用

    def test_equip_item_replaces_previous_equipment(self, sample_player, sample_equipment_items):
        """装備の付け替えで前の装備がインベントリに戻る"""
        helmet1 = sample_equipment_items["helmet"]
        
        # 新しいヘルメット作成
        helmet2_item = Item(
            item_id=10, name="銀のヘルメット", description="より良いヘルメット",
            price=200, type=ItemType.HELMET, rarity=Rarity.UNCOMMON
        )
        helmet2 = UniqueItem(id=10, item=helmet2_item, durability=120, defense=8)
        
        # 最初のヘルメットを装備
        sample_player.add_item(helmet1)
        sample_player.equip_item_from_inventory(helmet1.id)
        assert sample_player.equipment.helmet == helmet1
        assert sample_player.defense == 10  # 5 + 5
        
        # 2つ目のヘルメットに付け替え
        sample_player.add_item(helmet2)
        sample_player.equip_item_from_inventory(helmet2.id)
        assert sample_player.equipment.helmet == helmet2
        assert sample_player.defense == 13  # 5 + 8
        assert sample_player.has_unique_item(helmet1.id)  # 前の装備がインベントリに戻る

    def test_unequip_item_to_inventory(self, sample_player, sample_equipment_items):
        """装備を外してインベントリに戻せる"""
        helmet = sample_equipment_items["helmet"]
        
        # 装備
        sample_player.equipment.equip_helmet(helmet)
        assert sample_player.equipment.helmet == helmet
        assert sample_player.defense == 10
        
        # 脱装
        success = sample_player.unequip_item_to_inventory("helmet")
        assert success
        assert sample_player.equipment.helmet is None
        assert sample_player.defense == 5  # ベース値に戻る
        assert sample_player.has_unique_item(helmet.id)  # インベントリに戻る

    def test_cannot_equip_wrong_type_from_inventory(self, sample_player):
        """間違ったタイプのアイテムは装備できない"""
        # 消耗品を作成
        consumable_item = Item(
            item_id=20, name="回復薬", description="HPを回復する薬",
            price=50, type=ItemType.CONSUMABLE, rarity=Rarity.COMMON
        )
        consumable = UniqueItem(id=20, item=consumable_item, durability=1)
        
        sample_player.add_item(consumable)
        
        # 装備しようとするが失敗
        success = sample_player.equip_item_from_inventory(consumable.id)
        assert not success
        assert sample_player.has_unique_item(consumable.id)  # インベントリに残る

    def test_cannot_equip_broken_item_from_inventory(self, sample_player):
        """破損したアイテムは装備できない"""
        # 破損したヘルメット作成
        helmet_item = Item(
            item_id=30, name="壊れたヘルメット", description="耐久度がゼロのヘルメット",
            price=10, type=ItemType.HELMET, rarity=Rarity.COMMON
        )
        broken_helmet = UniqueItem(id=30, item=helmet_item, durability=0, defense=1)
        
        sample_player.add_item(broken_helmet)
        
        # 装備しようとするが失敗
        success = sample_player.equip_item_from_inventory(broken_helmet.id)
        assert not success
        assert sample_player.has_unique_item(broken_helmet.id)  # インベントリに残る

    def test_equipment_status_effects_combination(self, sample_player, sample_equipment_items):
        """装備ボーナスと状態異常効果の組み合わせ"""
        gloves = sample_equipment_items["gloves"]
        
        # グローブ装備（攻撃+3, 素早さ+2）
        sample_player.equipment.equip_gloves(gloves)
        
        # 状態異常追加（攻撃+5, 3ターン）
        sample_player.add_status_effect(StatusEffectType.ATTACK_UP, 3, 5)
        
        # 合計ステータス確認
        assert sample_player.attack == 18  # ベース10 + 装備3 + 効果5
        assert sample_player.speed == 9    # ベース7 + 装備2
        assert sample_player.defense == 5  # ベース5のみ

    def test_full_equipment_display(self, sample_player, sample_equipment_items):
        """全装備表示のテスト"""
        # 全装備装着
        sample_player.equipment.equip_helmet(sample_equipment_items["helmet"])
        sample_player.equipment.equip_chest(sample_equipment_items["chest"])
        sample_player.equipment.equip_gloves(sample_equipment_items["gloves"])
        sample_player.equipment.equip_shoes(sample_equipment_items["shoes"])
        
        display = sample_player.get_full_status_display()
        
        # 各要素が含まれているか確認
        assert "勇者" in display
        assert "攻撃力: 13" in display  # 10 + 3
        assert "防御力: 23" in display  # 5 + 5 + 10 + 3
        assert "素早さ: 10" in display  # 7 + 2 + 1
        assert "鉄のヘルメット" in display
        assert "鉄の胸当て" in display
        assert "革手袋" in display
        assert "革靴" in display

    def test_invalid_slot_type_unequip(self, sample_player):
        """無効なスロットタイプでの脱装"""
        success = sample_player.unequip_item_to_inventory("invalid_slot")
        assert not success

    def test_unequip_empty_slot(self, sample_player):
        """何も装備していないスロットの脱装"""
        success = sample_player.unequip_item_to_inventory("helmet")
        assert not success  # 何も装備していないので失敗
