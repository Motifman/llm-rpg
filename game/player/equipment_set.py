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
    
    def get_total_attack_bonus(self) -> int:
        total = 0
        if self.weapon:
            total += self.weapon.effect.attack_bonus
        return total
    
    def get_total_defense_bonus(self) -> int:
        total = 0
        for armor in [self.helmet, self.armor, self.shoes, self.gloves]:
            if armor:
                total += armor.effect.defense_bonus
        return total
    
    def get_total_speed_bonus(self) -> int:
        total = 0
        for armor in [self.helmet, self.armor, self.shoes, self.gloves]:
            if armor:
                total += armor.effect.speed_bonus
        return total
    
    def get_total_critical_rate(self) -> float:
        if self.weapon:
            return self.weapon.get_critical_rate()
        return 0.0
    
    def get_total_evasion_rate(self) -> float:
        total = 0.0
        for armor in [self.helmet, self.armor, self.shoes, self.gloves]:
            if armor:
                total += armor.get_evasion_bonus()
        return min(total, 0.95) 

    def get_total_status_resistance(self, status_effect_type: StatusEffectType) -> float:
        total = 0.0
        for armor in [self.helmet, self.armor, self.shoes, self.gloves]:
            if armor:
                total += armor.get_status_resistance(status_effect_type)
        return min(total, 0.95)

    def get_equipped_weapons(self) -> List[Weapon]:
        return [self.weapon] if self.weapon else []
    
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
            EquipmentSlot.ARMOR: self.armor,
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
            equipped_slots.append(EquipmentSlot.ARMOR)
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
            EquipmentSlot.ARMOR: "アーマー",
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
        elif armor.armor_type == ArmorType.ARMOR:
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
        elif armor_type == ArmorType.ARMOR:
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
        elif slot == EquipmentSlot.ARMOR:
            return self.unequip_armor(ArmorType.ARMOR)
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