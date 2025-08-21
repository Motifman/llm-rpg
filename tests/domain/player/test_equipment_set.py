import pytest
from src.domain.item.item import Item
from src.domain.item.equipment_item import EquipmentItem
from src.domain.item.durability import Durability
from src.domain.item.item_enum import ItemType, Rarity
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.base_status import BaseStatus
from src.domain.item.item_exception import ItemNotEquippableException


class TestEquipmentSet:
    """EquipmentSetクラスのテスト"""
    
    @pytest.fixture
    def equipment_set(self):
        """空の装備セットを作成"""
        return EquipmentSet()
    
    @pytest.fixture
    def sample_helmet(self):
        """サンプルヘルメットを作成"""
        item = Item(
            item_id=1,
            name="鉄のヘルメット",
            description="頑丈な鉄製のヘルメット",
            item_type=ItemType.HELMET,
            rarity=Rarity.COMMON
        )
        return EquipmentItem(
            item_id=1,
            name="鉄のヘルメット",
            description="頑丈な鉄製のヘルメット",
            item_type=ItemType.HELMET,
            rarity=Rarity.COMMON,
            unique_id=1,
            base_status=BaseStatus(attack=0, defense=5, speed=0, critical_rate=0.0, evasion_rate=0.0),
            durability=Durability(100, 100)
        )
    
    @pytest.fixture
    def sample_weapon(self):
        """サンプル武器を作成"""
        return EquipmentItem(
            item_id=2,
            name="鉄の剣",
            description="頑丈な鉄製の剣",
            item_type=ItemType.WEAPON,
            rarity=Rarity.COMMON,
            unique_id=2,
            base_status=BaseStatus(attack=10, defense=0, speed=0, critical_rate=0.05, evasion_rate=0.0),
            durability=Durability(80, 80)
        )
    
    @pytest.fixture
    def sample_chest(self):
        """サンプルチェストプレートを作成"""
        return EquipmentItem(
            item_id=3,
            name="鉄のチェストプレート",
            description="頑丈な鉄製の胸当て",
            item_type=ItemType.CHEST,
            rarity=Rarity.COMMON,
            unique_id=3,
            base_status=BaseStatus(attack=0, defense=10, speed=0, critical_rate=0.0, evasion_rate=0.0),
            durability=Durability(150, 150)
        )
    
    @pytest.fixture
    def sample_gloves(self):
        """サンプルグローブを作成"""
        return EquipmentItem(
            item_id=4,
            name="革のグローブ",
            description="柔軟な革製のグローブ",
            item_type=ItemType.GLOVES,
            rarity=Rarity.COMMON,
            unique_id=4,
            base_status=BaseStatus(attack=2, defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0),
            durability=Durability(80, 80)
        )
    
    @pytest.fixture
    def sample_shoes(self):
        """サンプルシューズを作成"""
        return EquipmentItem(
            item_id=5,
            name="革のブーツ",
            description="頑丈な革製のブーツ",
            item_type=ItemType.SHOES,
            rarity=Rarity.COMMON,
            unique_id=5,
            base_status=BaseStatus(attack=0, defense=3, speed=2, critical_rate=0.0, evasion_rate=0.0),
            durability=Durability(120, 120)
        )
    
    @pytest.fixture
    def broken_helmet(self):
        """破損したヘルメットを作成"""
        return EquipmentItem(
            item_id=6,
            name="壊れたヘルメット",
            description="耐久度がゼロのヘルメット",
            item_type=ItemType.HELMET,
            rarity=Rarity.COMMON,
            unique_id=6,
            base_status=BaseStatus(attack=0, defense=1, speed=0, critical_rate=0.0, evasion_rate=0.0),
            durability=Durability(0, 100)
        )
    
    @pytest.fixture
    def wrong_type_item(self):
        """装備できないタイプのアイテムを作成"""
        return EquipmentItem(
            item_id=7,
            name="消耗品",
            description="装備できないアイテム",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            unique_id=7,
            base_status=BaseStatus(attack=0, defense=0, speed=0, critical_rate=0.0, evasion_rate=0.0),
            durability=Durability(1, 1)
        )

    def test_initial_state(self, equipment_set):
        """初期状態のテスト"""
        assert equipment_set._weapon is None
        assert equipment_set._helmet is None
        assert equipment_set._chest is None
        assert equipment_set._gloves is None
        assert equipment_set._shoes is None

    def test_equip_helmet(self, equipment_set, sample_helmet):
        """ヘルメット装備のテスト"""
        previous = equipment_set.equip_item(sample_helmet)
        
        assert previous is None  # 最初は何も装備していない
        assert equipment_set._helmet == sample_helmet

    def test_equip_weapon(self, equipment_set, sample_weapon):
        """武器装備のテスト"""
        previous = equipment_set.equip_item(sample_weapon)
        
        assert previous is None
        assert equipment_set._weapon == sample_weapon

    def test_equip_chest(self, equipment_set, sample_chest):
        """チェストプレート装備のテスト"""
        previous = equipment_set.equip_item(sample_chest)
        
        assert previous is None
        assert equipment_set._chest == sample_chest

    def test_equip_gloves(self, equipment_set, sample_gloves):
        """グローブ装備のテスト"""
        previous = equipment_set.equip_item(sample_gloves)
        
        assert previous is None
        assert equipment_set._gloves == sample_gloves

    def test_equip_shoes(self, equipment_set, sample_shoes):
        """シューズ装備のテスト"""
        previous = equipment_set.equip_item(sample_shoes)
        
        assert previous is None
        assert equipment_set._shoes == sample_shoes

    def test_replace_equipment(self, equipment_set, sample_helmet):
        """装備の付け替えテスト"""
        # 最初の装備
        equipment_set.equip_item(sample_helmet)
        
        # 新しいヘルメット
        new_helmet = EquipmentItem(
            item_id=10,
            name="新しいヘルメット",
            description="より良いヘルメット",
            item_type=ItemType.HELMET,
            rarity=Rarity.UNCOMMON,
            unique_id=10,
            base_status=BaseStatus(attack=0, defense=8, speed=0, critical_rate=0.0, evasion_rate=0.0),
            durability=Durability(120, 120)
        )
        
        # 付け替え
        previous = equipment_set.equip_item(new_helmet)
        
        assert previous == sample_helmet
        assert equipment_set._helmet == new_helmet

    def test_unequip_helmet(self, equipment_set, sample_helmet):
        """ヘルメット脱装のテスト"""
        equipment_set.equip_item(sample_helmet)
        
        removed = equipment_set.unequip_item(ItemType.HELMET)
        
        assert removed == sample_helmet
        assert equipment_set._helmet is None

    def test_unequip_empty_slot(self, equipment_set):
        """何も装備していないスロットの脱装テスト"""
        removed = equipment_set.unequip_item(ItemType.HELMET)
        assert removed is None

    def test_calculate_status(self, equipment_set, sample_weapon, sample_helmet, sample_chest, sample_gloves, sample_shoes):
        """全装備時のステータス計算テスト"""
        equipment_set.equip_item(sample_weapon)
        equipment_set.equip_item(sample_helmet)
        equipment_set.equip_item(sample_chest)
        equipment_set.equip_item(sample_gloves)
        equipment_set.equip_item(sample_shoes)
        
        total_status = equipment_set.calculate_status()
        
        # 合計ボーナス: 攻撃12(10+2), 防御18(5+10+3), 素早さ3(1+2), クリティカル率0.05
        assert total_status.attack == 12
        assert total_status.defense == 18
        assert total_status.speed == 3
        assert total_status.critical_rate == 0.05

    def test_equip_wrong_type(self, equipment_set, wrong_type_item):
        """間違ったタイプのアイテム装備エラーテスト"""
        with pytest.raises(ValueError, match="Invalid item type"):
            equipment_set.equip_item(wrong_type_item)

    def test_equip_broken_item(self, equipment_set, broken_helmet):
        """破損したアイテムの装備エラーテスト"""
        with pytest.raises(ItemNotEquippableException):
            equipment_set.equip_item(broken_helmet)

    def test_invalid_unequip_type(self, equipment_set):
        """無効なタイプでの脱装エラーテスト"""
        with pytest.raises(ItemNotEquippableException):
            equipment_set.unequip_item(ItemType.CONSUMABLE)