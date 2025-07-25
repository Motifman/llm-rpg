from typing import Optional, TYPE_CHECKING
from game.player.inventory import Inventory
from game.player.equipment_set import EquipmentSet
from game.player.status import Status
from game.item.item import Item
from game.item.equipment_item import Weapon, Armor
from game.enums import Role, EquipmentSlot

# 型ヒントの遅延インポート
if TYPE_CHECKING:
    from game.action.actions.item_action import ItemUseResult, ConsumableItem, ItemEffect
    from game.action.actions.equipment_action import EquipItemResult, UnequipItemResult


class Player:
    def __init__(self, player_id: str, name: str, role: Role):
        self.player_id = player_id
        self.name = name
        self.role = role
        self.current_spot_id = None
        self.inventory = Inventory()
        self.equipment = EquipmentSet()
        self.status = Status()
        self.current_spot_id = None
    
    def get_player_id(self) -> str:
        return self.player_id

    def get_current_spot_id(self) -> str:
        return self.current_spot_id
    
    def set_current_spot_id(self, spot_id: str):
        self.current_spot_id = spot_id
    
    def get_role(self) -> Role:
        return self.role
    
    def set_role(self, role: Role):
        self.role = role
    
    def is_role(self, role: Role) -> bool:
        return self.role == role
    
    def get_inventory(self) -> Inventory:
        return self.inventory
    
    def set_inventory(self, inventory: Inventory):
        self.inventory = inventory
    
    def get_equipment(self) -> EquipmentSet:
        return self.equipment
    
    def set_equipment(self, equipment: EquipmentSet):
        self.equipment = equipment
    
    def get_status(self) -> Status:
        return self.status
    
    def set_status(self, status: Status):
        self.status = status

    def get_current_status_snapshot(self) -> dict:
        return {
            'hp': self.status.get_hp(),
            'mp': self.status.get_mp(),
            'attack': self.status.get_attack(),
            'defense': self.status.get_defense(),
            'money': self.status.get_money(),
            'experience_points': self.status.get_experience_points()
        }

    def use_item(self, item_id: str) -> 'ItemUseResult':
        from game.action.actions.item_action import ItemUseResult, ConsumableItem, ItemEffect
        
        item = self.inventory.get_item_by_id(item_id)
        if item is None:
            return ItemUseResult(False, "アイテムが見つかりません", item_id)
        
        if not isinstance(item, ConsumableItem):
            return ItemUseResult(False, "アイテムが使用できません", item_id)
        
        if not item.can_consume(self):
            return ItemUseResult(False, "アイテムが使用できません", item_id)
        
        status_before = self.get_current_status_snapshot()
        
        self.inventory.remove_item(item)
        self.status.apply_item_effect(item.effect)
        
        status_after = self.get_current_status_snapshot()
        
        return ItemUseResult(
            success=True,
            message="アイテムを使用しました",
            item_id=item_id,
            effect=item.effect,
            status_before=status_before,
            status_after=status_after
        )
    
    def preview_item_effect(self, item_id: str) -> Optional['ItemEffect']:
        from game.action.actions.item_action import ConsumableItem, ItemEffect
        
        item = self.inventory.get_item_by_id(item_id)
        if item is None or not isinstance(item, ConsumableItem):
            return None
        return item.effect

    def has_item(self, item_id: str) -> bool:
        return self.inventory.has_item(item_id)
    
    def equip_item(self, item_id: str) -> 'EquipItemResult':
        from game.action.actions.equipment_action import EquipItemResult
        
        item = self.inventory.get_item_by_id(item_id)
        if item is None:
            return EquipItemResult(False, "アイテムが見つかりません", str(self.equipment), item_id, None)
        self.inventory.remove_item_by_id(item.item_id, 1)
        if isinstance(item, Weapon):
            old_weapon = self.equipment.equip_weapon(item)
            if old_weapon:
                self.inventory.add_item(old_weapon)
            return EquipItemResult(True, "武器を装備しました", str(self.equipment), item.item_id, old_weapon.item_id if old_weapon else None)
        elif isinstance(item, Armor):
            old_armor = self.equipment.equip_armor(item)
            if old_armor:
                self.inventory.add_item(old_armor)
            return EquipItemResult(True, "防具を装備しました", str(self.equipment), item.item_id, old_armor.item_id if old_armor else None)
        else:
            return EquipItemResult(False, "アイテムを装備できません", str(self.equipment), item.item_id, None)  
    
    def unequip_slot(self, slot: EquipmentSlot) -> 'UnequipItemResult':
        from game.action.actions.equipment_action import UnequipItemResult
        
        item = self.equipment.unequip_slot(slot)
        if item:
            self.inventory.add_item(item)
            slot_name = self.equipment.get_slot_name(slot)
            return UnequipItemResult(True, f"{slot_name}を外しました", str(self.equipment), item.item_id)
        else:
            slot_name = self.equipment.get_slot_name(slot)
            return UnequipItemResult(False, f"{slot_name}を装備していないため外せません", str(self.equipment), None)
    
    @property
    def hp(self) -> int:
        return self.status.get_hp()
    
    @property
    def mp(self) -> int:
        return self.status.get_mp()
    
    @property
    def attack(self) -> int:
        return self.status.get_attack() + self.equipment.get_total_attack_bonus()
    
    @property
    def defense(self) -> int:
        return self.status.get_defense() + self.equipment.get_total_defense_bonus()
    
    @property
    def speed(self) -> int:
        return self.status.get_speed() + self.equipment.get_total_speed_bonus()
    
    @property
    def critical_rate(self) -> float:
        return self.status.get_critical_rate() + self.equipment.get_total_critical_rate()

    @property
    def evasion_rate(self) -> float:
        return self.status.get_evasion_rate() + self.equipment.get_total_evasion_rate()
    
    def get_status_summary(self) -> str:
        return (f"HP: {self.hp}/{self.status.get_max_hp()}, "
                f"MP: {self.mp}/{self.status.get_max_mp()}, "
                f"攻撃: {self.attack}, 防御: {self.defense}, 素早さ: {self.speed}, "
                f"クリティカル: {self.critical_rate:.1%}, 回避: {self.evasion_rate:.1%}")
    