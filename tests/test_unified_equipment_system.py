import pytest
from game.player.equipment_set import EquipmentSet
from game.player.player import Player
from game.item.equipment_item import Weapon, Armor, WeaponEffect, ArmorEffect
from game.enums import EquipmentSlot, ArmorType, Role, WeaponType
from game.action.actions.equipment_action import UnequipItemStrategy, UnequipItemCommand


class TestUnifiedEquipmentSystem:
    """統一的な装備システムのテスト"""
    
    def setup_method(self):
        """テスト前のセットアップ"""
        self.player = Player("test_player", "テストプレイヤー", Role.ADVENTURER)
        self.equipment = self.player.get_equipment()
        
        # テスト用の装備アイテムを作成
        self.weapon = Weapon(
            item_id="test_sword",
            name="テスト用の剣",
            description="テスト用の剣",
            weapon_type=WeaponType.SWORD,
            effect=WeaponEffect(attack_bonus=10, critical_rate_bonus=0.1)
        )
        
        self.helmet = Armor(
            item_id="test_helmet",
            name="テスト用のヘルメット",
            description="テスト用のヘルメット",
            armor_type=ArmorType.HELMET,
            effect=ArmorEffect(defense_bonus=5, speed_bonus=2)
        )
        
        self.armor = Armor(
            item_id="test_armor",
            name="テスト用のアーマー",
            description="テスト用のアーマー",
            armor_type=ArmorType.CHEST,
            effect=ArmorEffect(defense_bonus=8, speed_bonus=1)
        )
    
    def test_equipment_slot_enum(self):
        """EquipmentSlotの列挙値が正しく定義されていることを確認"""
        assert EquipmentSlot.WEAPON.value == "weapon"
        assert EquipmentSlot.HELMET.value == "helmet"
        assert EquipmentSlot.CHEST.value == "chest"
        assert EquipmentSlot.SHOES.value == "shoes"
        assert EquipmentSlot.GLOVES.value == "gloves"
    
    def test_get_equipped_slots_empty(self):
        """装備していない場合のget_equipped_slots"""
        equipped_slots = self.equipment.get_equipped_slots()
        assert len(equipped_slots) == 0
    
    def test_get_equipped_slots_with_equipment(self):
        """装備がある場合のget_equipped_slots"""
        # 武器とヘルメットを装備
        self.equipment.equip_weapon(self.weapon)
        self.equipment.equip_armor(self.helmet)
        
        equipped_slots = self.equipment.get_equipped_slots()
        assert len(equipped_slots) == 2
        assert EquipmentSlot.WEAPON in equipped_slots
        assert EquipmentSlot.HELMET in equipped_slots
    
    def test_get_available_slots(self):
        """get_available_slotsが全てのスロットを返すことを確認"""
        available_slots = self.equipment.get_available_slots()
        assert len(available_slots) == 5
        assert EquipmentSlot.WEAPON in available_slots
        assert EquipmentSlot.HELMET in available_slots
        assert EquipmentSlot.CHEST in available_slots
        assert EquipmentSlot.SHOES in available_slots
        assert EquipmentSlot.GLOVES in available_slots
    
    def test_get_slot_name(self):
        """get_slot_nameが正しい日本語名を返すことを確認"""
        assert self.equipment.get_slot_name(EquipmentSlot.WEAPON) == "武器"
        assert self.equipment.get_slot_name(EquipmentSlot.HELMET) == "ヘルメット"
        assert self.equipment.get_slot_name(EquipmentSlot.CHEST) == "アーマー"
        assert self.equipment.get_slot_name(EquipmentSlot.SHOES) == "シューズ"
        assert self.equipment.get_slot_name(EquipmentSlot.GLOVES) == "グローブ"
    
    def test_unequip_slot_weapon(self):
        """武器スロットの装備解除"""
        self.equipment.equip_weapon(self.weapon)
        
        unequipped_item = self.equipment.unequip_slot(EquipmentSlot.WEAPON)
        assert unequipped_item == self.weapon
        assert self.equipment.weapon is None
    
    def test_unequip_slot_armor(self):
        """防具スロットの装備解除"""
        self.equipment.equip_armor(self.helmet)
        
        unequipped_item = self.equipment.unequip_slot(EquipmentSlot.HELMET)
        assert unequipped_item == self.helmet
        assert self.equipment.helmet is None
    
    def test_unequip_slot_empty(self):
        """装備していないスロットの装備解除"""
        unequipped_item = self.equipment.unequip_slot(EquipmentSlot.WEAPON)
        assert unequipped_item is None
    
    def test_player_unequip_slot(self):
        """Playerクラスのunequip_slotメソッド"""
        # 武器を装備
        self.player.get_inventory().add_item(self.weapon)
        equip_result = self.player.equip_item(self.weapon.item_id)
        assert equip_result.success
        
        # 武器を外す
        unequip_result = self.player.unequip_slot(EquipmentSlot.WEAPON)
        assert unequip_result.success
        assert unequip_result.equipment_name == self.weapon.item_id
        assert "武器を外しました" in unequip_result.message
    
    def test_player_unequip_slot_empty(self):
        """装備していないスロットを外そうとした場合"""
        unequip_result = self.player.unequip_slot(EquipmentSlot.WEAPON)
        assert not unequip_result.success
        assert "装備していないため外せません" in unequip_result.message
    
    def test_unequip_item_strategy_get_required_arguments(self):
        """UnequipItemStrategyのget_required_argumentsメソッド"""
        strategy = UnequipItemStrategy()
        
        # 装備していない場合
        required_args = strategy.get_required_arguments(self.player, None)
        assert len(required_args) == 0
        
        # 武器を装備した場合
        self.player.get_inventory().add_item(self.weapon)
        self.player.equip_item(self.weapon.item_id)
        
        required_args = strategy.get_required_arguments(self.player, None)
        assert len(required_args) == 1
        argument_info = required_args[0]
        assert argument_info.name == "slot_name"
        assert argument_info.description == "装備を外すスロットを選択してください"
        assert "weapon" in argument_info.candidates
    
    def test_unequip_item_command_valid_slot(self):
        """有効なスロットでのUnequipItemCommand"""
        # 武器を装備
        self.player.get_inventory().add_item(self.weapon)
        self.player.equip_item(self.weapon.item_id)
        
        command = UnequipItemCommand(EquipmentSlot.WEAPON)
        result = command.execute(self.player, None)
        
        assert result.success
        assert result.equipment_name == self.weapon.item_id
    
    def test_unequip_item_command_invalid_slot(self):
        """無効なスロットでのUnequipItemCommand"""
        command = UnequipItemCommand(None)
        result = command.execute(self.player, None)
        
        assert not result.success
        assert "無効な装備スロットです" in result.message
    
    def test_unequip_item_strategy_build_command(self):
        """UnequipItemStrategyのbuild_action_commandメソッド"""
        strategy = UnequipItemStrategy()
        
        # 有効なスロット名
        command = strategy.build_action_command(self.player, None, "weapon")
        assert isinstance(command, UnequipItemCommand)
        assert command.slot == EquipmentSlot.WEAPON
        
        # 無効なスロット名
        command = strategy.build_action_command(self.player, None, "invalid_slot")
        assert isinstance(command, UnequipItemCommand)
        assert command.slot is None 