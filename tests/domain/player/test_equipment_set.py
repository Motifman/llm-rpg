import pytest
from domain.item.item import Item
from domain.item.unique_item import UniqueItem
from domain.item.enum import ItemType, Rarity
from domain.player.equipment_set import EquipmentSet


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
            price=100,
            type=ItemType.HELMET,
            rarity=Rarity.COMMON
        )
        return UniqueItem(id=1, item=item, durability=100, defense=5)
    
    @pytest.fixture
    def sample_chest(self):
        """サンプルチェストプレートを作成"""
        item = Item(
            item_id=2,
            name="鉄のチェストプレート",
            description="頑丈な鉄製の胸当て",
            price=200,
            type=ItemType.CHEST,
            rarity=Rarity.COMMON
        )
        return UniqueItem(id=2, item=item, durability=150, defense=10)
    
    @pytest.fixture
    def sample_gloves(self):
        """サンプルグローブを作成"""
        item = Item(
            item_id=3,
            name="革のグローブ",
            description="柔軟な革製のグローブ",
            price=50,
            type=ItemType.GLOVES,
            rarity=Rarity.COMMON
        )
        return UniqueItem(id=3, item=item, durability=80, attack=2, speed=1)
    
    @pytest.fixture
    def sample_shoes(self):
        """サンプルシューズを作成"""
        item = Item(
            item_id=4,
            name="革のブーツ",
            description="頑丈な革製のブーツ",
            price=75,
            type=ItemType.SHOES,
            rarity=Rarity.COMMON
        )
        return UniqueItem(id=4, item=item, durability=120, defense=3, speed=2)
    
    @pytest.fixture
    def broken_helmet(self):
        """破損したヘルメットを作成"""
        item = Item(
            item_id=5,
            name="壊れたヘルメット",
            description="耐久度がゼロのヘルメット",
            price=10,
            type=ItemType.HELMET,
            rarity=Rarity.COMMON
        )
        return UniqueItem(id=5, item=item, durability=0, defense=1)
    
    @pytest.fixture
    def wrong_type_item(self):
        """装備できないタイプのアイテムを作成"""
        item = Item(
            item_id=6,
            name="消耗品",
            description="装備できないアイテム",
            price=5,
            type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON
        )
        return UniqueItem(id=6, item=item, durability=1)

    def test_initial_state(self, equipment_set):
        """初期状態のテスト"""
        assert equipment_set.helmet is None
        assert equipment_set.chest is None
        assert equipment_set.gloves is None
        assert equipment_set.shoes is None
        assert equipment_set.is_empty()
        assert equipment_set.get_equipped_count() == 0
        assert equipment_set.get_attack_bonus() == 0
        assert equipment_set.get_defense_bonus() == 0
        assert equipment_set.get_speed_bonus() == 0
        assert not equipment_set.has_broken_equipment()
        assert equipment_set.get_broken_equipment() == []

    def test_equip_helmet(self, equipment_set, sample_helmet):
        """ヘルメット装備のテスト"""
        previous = equipment_set.equip_helmet(sample_helmet)
        
        assert previous is None  # 最初は何も装備していない
        assert equipment_set.helmet == sample_helmet
        assert not equipment_set.is_empty()
        assert equipment_set.get_equipped_count() == 1
        assert equipment_set.get_defense_bonus() == 5

    def test_equip_chest(self, equipment_set, sample_chest):
        """チェストプレート装備のテスト"""
        previous = equipment_set.equip_chest(sample_chest)
        
        assert previous is None
        assert equipment_set.chest == sample_chest
        assert equipment_set.get_defense_bonus() == 10

    def test_equip_gloves(self, equipment_set, sample_gloves):
        """グローブ装備のテスト"""
        previous = equipment_set.equip_gloves(sample_gloves)
        
        assert previous is None
        assert equipment_set.gloves == sample_gloves
        assert equipment_set.get_attack_bonus() == 2
        assert equipment_set.get_speed_bonus() == 1

    def test_equip_shoes(self, equipment_set, sample_shoes):
        """シューズ装備のテスト"""
        previous = equipment_set.equip_shoes(sample_shoes)
        
        assert previous is None
        assert equipment_set.shoes == sample_shoes
        assert equipment_set.get_defense_bonus() == 3
        assert equipment_set.get_speed_bonus() == 2

    def test_replace_equipment(self, equipment_set, sample_helmet):
        """装備の付け替えテスト"""
        # 最初の装備
        equipment_set.equip_helmet(sample_helmet)
        
        # 新しいヘルメット
        new_helmet_item = Item(
            item_id=10,
            name="新しいヘルメット",
            description="より良いヘルメット",
            price=200,
            type=ItemType.HELMET,
            rarity=Rarity.UNCOMMON
        )
        new_helmet = UniqueItem(id=10, item=new_helmet_item, durability=120, defense=8)
        
        # 付け替え
        previous = equipment_set.equip_helmet(new_helmet)
        
        assert previous == sample_helmet
        assert equipment_set.helmet == new_helmet
        assert equipment_set.get_defense_bonus() == 8

    def test_unequip_helmet(self, equipment_set, sample_helmet):
        """ヘルメット脱装のテスト"""
        equipment_set.equip_helmet(sample_helmet)
        
        removed = equipment_set.unequip_helmet()
        
        assert removed == sample_helmet
        assert equipment_set.helmet is None
        assert equipment_set.get_defense_bonus() == 0

    def test_unequip_empty_slot(self, equipment_set):
        """何も装備していないスロットの脱装テスト"""
        removed = equipment_set.unequip_helmet()
        assert removed is None

    def test_full_equipment_bonuses(self, equipment_set, sample_helmet, sample_chest, sample_gloves, sample_shoes):
        """全装備時のボーナス計算テスト"""
        equipment_set.equip_helmet(sample_helmet)
        equipment_set.equip_chest(sample_chest)
        equipment_set.equip_gloves(sample_gloves)
        equipment_set.equip_shoes(sample_shoes)
        
        # 合計ボーナス: 攻撃2, 防御18(5+10+3), 素早さ3(1+2)
        assert equipment_set.get_attack_bonus() == 2
        assert equipment_set.get_defense_bonus() == 18
        assert equipment_set.get_speed_bonus() == 3
        assert equipment_set.get_equipped_count() == 4
        assert not equipment_set.is_empty()

    def test_equip_wrong_type(self, equipment_set, wrong_type_item):
        """間違ったタイプのアイテム装備エラーテスト"""
        with pytest.raises(ValueError, match="ヘルメット以外のアイテムは装備できません"):
            equipment_set.equip_helmet(wrong_type_item)

    def test_equip_broken_item(self, equipment_set, broken_helmet):
        """破損したアイテムの装備エラーテスト"""
        with pytest.raises(ValueError, match="ヘルメット以外のアイテムは装備できません"):
            equipment_set.equip_helmet(broken_helmet)

    def test_broken_equipment_detection(self, equipment_set, sample_helmet):
        """破損装備の検出テスト"""
        equipment_set.equip_helmet(sample_helmet)
        
        # 装備を破損させる
        sample_helmet.use_durability(100)  # 耐久度を0にする
        
        assert equipment_set.has_broken_equipment()
        broken_items = equipment_set.get_broken_equipment()
        assert len(broken_items) == 1
        assert broken_items[0] == sample_helmet

    def test_equipment_display(self, equipment_set, sample_helmet, sample_gloves):
        """装備表示のテスト"""
        equipment_set.equip_helmet(sample_helmet)
        equipment_set.equip_gloves(sample_gloves)
        
        display = equipment_set.get_equipment_display()
        
        assert "=== 装備 ===" in display
        assert "鉄のヘルメット" in display
        assert "革のグローブ" in display
        assert "チェストプレート: なし" in display
        assert "シューズ: なし" in display
        assert "合計ボーナス: 攻撃+2 防御+5 素早さ+1" in display

    def test_empty_equipment_display(self, equipment_set):
        """空の装備表示テスト"""
        display = equipment_set.get_equipment_display()
        
        assert "=== 装備 ===" in display
        assert "ヘルメット: なし" in display
        assert "チェストプレート: なし" in display
        assert "グローブ: なし" in display
        assert "シューズ: なし" in display
        assert "合計ボーナス: 攻撃+0 防御+0 素早さ+0" in display

    def test_equipment_with_no_bonuses(self, equipment_set):
        """ボーナスなしの装備テスト"""
        # ボーナスなしのアイテム
        item = Item(
            item_id=20,
            name="装飾用ヘルメット",
            description="見た目だけのヘルメット",
            price=10,
            type=ItemType.HELMET,
            rarity=Rarity.COMMON
        )
        # attack, defense, speed すべてNone
        equipment = UniqueItem(id=20, item=item, durability=50)
        
        equipment_set.equip_helmet(equipment)
        
        assert equipment_set.get_attack_bonus() == 0
        assert equipment_set.get_defense_bonus() == 0
        assert equipment_set.get_speed_bonus() == 0
