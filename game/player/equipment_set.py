from dataclasses import dataclass
from typing import List, Optional, Dict

from game.item.equipment_item import Weapon, Armor, ArmorType
from game.enums import StatusEffectType, EquipmentSlot


@dataclass
class EquipmentSet:
    weapon: Optional[Weapon] = None
    helmet: Optional[Armor] = None
    armor: Optional[Armor] = None
    shoes: Optional[Armor] = None
    gloves: Optional[Armor] = None
    
    def get_equipment_bonuses(self) -> dict:
        """装備によるボーナスを取得（戦闘計算用）"""
        bonuses = {
            'attack_bonus': 0,
            'defense_bonus': 0,
            'speed_bonus': 0,
            'critical_rate': 0.0,
            'evasion_rate': 0.0,
            'status_resistance': {}
        }
        
        # 武器ボーナス
        if self.weapon:
            bonuses['attack_bonus'] += self.weapon.get_attack_bonus()
            bonuses['critical_rate'] += self.weapon.get_critical_rate()
        
        # 防具ボーナス
        for armor in [self.helmet, self.armor, self.shoes, self.gloves]:
            if armor:
                bonuses['defense_bonus'] += armor.get_defense_bonus()
                bonuses['speed_bonus'] += armor.get_speed_bonus()
                bonuses['evasion_rate'] += armor.get_evasion_bonus()
                
                # 状態異常耐性
                for status_type in StatusEffectType:
                    resistance = armor.get_status_resistance(status_type)
                    if resistance > 0:
                        if status_type not in bonuses['status_resistance']:
                            bonuses['status_resistance'][status_type] = 0.0
                        bonuses['status_resistance'][status_type] += resistance
        
        # 上限調整
        bonuses['evasion_rate'] = min(bonuses['evasion_rate'], 0.95)
        for status_type in bonuses['status_resistance']:
            bonuses['status_resistance'][status_type] = min(bonuses['status_resistance'][status_type], 0.95)
        
        return bonuses

    def get_equipped_weapons(self) -> List[Weapon]:
        return [self.weapon] if self.weapon else []
    
    def get_equipped_weapon(self) -> Optional[Weapon]:
        return self.weapon
    
    def get_equipped_armors(self) -> List[Armor]:
        armors = []
        for armor in [self.helmet, self.armor, self.shoes, self.gloves]:
            if armor:
                armors.append(armor)
        return armors
    
    def get_equipped_items(self) -> Dict[EquipmentSlot, Optional[Weapon | Armor]]:
        """統一的な装備アイテムの取得"""
        return {
            EquipmentSlot.WEAPON: self.weapon,
            EquipmentSlot.HELMET: self.helmet,
            EquipmentSlot.CHEST: self.armor,
            EquipmentSlot.SHOES: self.shoes,
            EquipmentSlot.GLOVES: self.gloves,
        }
    
    def get_equipped_slots(self) -> List[EquipmentSlot]:
        """装備されているスロットの一覧を取得"""
        equipped_slots = []
        if self.weapon:
            equipped_slots.append(EquipmentSlot.WEAPON)
        if self.helmet:
            equipped_slots.append(EquipmentSlot.HELMET)
        if self.armor:
            equipped_slots.append(EquipmentSlot.CHEST)
        if self.shoes:
            equipped_slots.append(EquipmentSlot.SHOES)
        if self.gloves:
            equipped_slots.append(EquipmentSlot.GLOVES)
        return equipped_slots
    
    def get_available_slots(self) -> List[EquipmentSlot]:
        """装備可能なスロットの一覧を取得（常に全てのスロット）"""
        return list(EquipmentSlot)
    
    def get_slot_name(self, slot: EquipmentSlot) -> str:
        """スロットの日本語名を取得"""
        slot_names = {
            EquipmentSlot.WEAPON: "武器",
            EquipmentSlot.HELMET: "ヘルメット",
            EquipmentSlot.CHEST: "アーマー",
            EquipmentSlot.SHOES: "シューズ",
            EquipmentSlot.GLOVES: "グローブ",
        }
        return slot_names.get(slot, str(slot.value))
    
    def equip_weapon(self, weapon: Weapon) -> Optional[Weapon]:
        previous = self.weapon
        self.weapon = weapon
        return previous
    
    def equip_armor(self, armor: Armor) -> Optional[Armor]:
        previous = None
        if armor.armor_type == ArmorType.HELMET:
            previous = self.helmet
            self.helmet = armor
        elif armor.armor_type == ArmorType.CHEST:
            previous = self.armor
            self.armor = armor
        elif armor.armor_type == ArmorType.SHOES:
            previous = self.shoes
            self.shoes = armor
        elif armor.armor_type == ArmorType.GLOVES:
            previous = self.gloves
            self.gloves = armor
        return previous
    
    def unequip_weapon(self) -> Optional[Weapon]:
        weapon = self.weapon
        self.weapon = None
        return weapon
    
    def unequip_armor(self, armor_type: ArmorType) -> Optional[Armor]:
        if armor_type == ArmorType.HELMET:
            armor = self.helmet
            self.helmet = None
            return armor
        elif armor_type == ArmorType.CHEST:
            armor = self.armor
            self.armor = None
            return armor
        elif armor_type == ArmorType.SHOES:
            armor = self.shoes
            self.shoes = None
            return armor
        elif armor_type == ArmorType.GLOVES:
            armor = self.gloves
            self.gloves = None
            return armor
        return None
    
    def unequip_slot(self, slot: EquipmentSlot) -> Optional[Weapon | Armor]:
        """統一的な装備解除メソッド"""
        if slot == EquipmentSlot.WEAPON:
            return self.unequip_weapon()
        elif slot == EquipmentSlot.HELMET:
            return self.unequip_armor(ArmorType.HELMET)
        elif slot == EquipmentSlot.CHEST:
            return self.unequip_armor(ArmorType.CHEST)
        elif slot == EquipmentSlot.SHOES:
            return self.unequip_armor(ArmorType.SHOES)
        elif slot == EquipmentSlot.GLOVES:
            return self.unequip_armor(ArmorType.GLOVES)
        return None
    
    def __str__(self):
        equipped = []
        if self.weapon:
            equipped.append(f"武器: {self.weapon.item_id}")
        if self.helmet:
            equipped.append(f"頭: {self.helmet.item_id}")
        if self.armor:
            equipped.append(f"体: {self.armor.item_id}")
        if self.shoes:
            equipped.append(f"足: {self.shoes.item_id}")
        if self.gloves:
            equipped.append(f"手: {self.gloves.item_id}")
        
        return "装備: " + ", ".join(equipped) if equipped else "装備なし" 