from __future__ import annotations

from typing import Optional
from src.domain.item.equipment_item import EquipmentItem
from src.domain.item.enum.item_enum import ItemType
from src.domain.item.exception.item_exception import ItemNotEquippableException
from src.domain.player.base_status import BaseStatus


class EquipmentSet:
    """プレイヤーの装備セット"""
    
    def __init__(self) -> None:
        self._weapon: Optional[EquipmentItem] = None
        self._helmet: Optional[EquipmentItem] = None
        self._chest: Optional[EquipmentItem] = None
        self._gloves: Optional[EquipmentItem] = None
        self._shoes: Optional[EquipmentItem] = None

    def equip_item(self, item: EquipmentItem) -> Optional[EquipmentItem]:
        """アイテムを装備"""
        if not isinstance(item, EquipmentItem):
            raise ItemNotEquippableException(f"Invalid item type: {type(item)}")
        if item.is_broken():
            raise ItemNotEquippableException(f"Item is broken: {item.item.name}")
        
        if item.item_type == ItemType.WEAPON:
            previous_equipment = self._weapon
            self._weapon = item
        elif item.item_type == ItemType.HELMET:
            previous_equipment = self._helmet
            self._helmet = item
        elif item.item_type == ItemType.CHEST:
            previous_equipment = self._chest
            self._chest = item
        elif item.item_type == ItemType.GLOVES:
            previous_equipment = self._gloves
            self._gloves = item
        elif item.item_type == ItemType.SHOES:
            previous_equipment = self._shoes
            self._shoes = item
        else:
            raise ValueError(f"Invalid item type: {item.item_type}")
        return previous_equipment
    
    def unequip_item(self, item_type: ItemType) -> Optional[EquipmentItem]:
        """アイテムを脱装"""
        if item_type == ItemType.WEAPON:
            previous_equipment = self._weapon
            self._weapon = None
        elif item_type == ItemType.HELMET:
            previous_equipment = self._helmet
            self._helmet = None
        elif item_type == ItemType.CHEST:
            previous_equipment = self._chest
            self._chest = None
        elif item_type == ItemType.GLOVES:
            previous_equipment = self._gloves
            self._gloves = None
        elif item_type == ItemType.SHOES:
            previous_equipment = self._shoes
            self._shoes = None
        else:
            raise ItemNotEquippableException(f"Invalid item type: {item_type}")
        return previous_equipment

    def calculate_status(self) -> BaseStatus:
        """装備によるステータスボーナスを計算"""
        total_status = BaseStatus(attack=0, defense=0, speed=0, critical_rate=0.0, evasion_rate=0.0)
        
        if self._weapon:
            total_status = total_status + self._weapon.base_status
        if self._helmet:
            total_status = total_status + self._helmet.base_status
        if self._chest:
            total_status = total_status + self._chest.base_status
        if self._gloves:
            total_status = total_status + self._gloves.base_status
        if self._shoes:
            total_status = total_status + self._shoes.base_status
            
        return total_status


# class EquipmentSet:
#     """プレイヤーの装備セット
    
#     ヘルメット、チェストプレート、グローブ、シューズの4種類の防具を装着可能。
#     武器は将来的に追加予定。
#     装備による攻撃力、防御力、素早さのボーナスを計算する。
#     """
    
#     def __init__(self) -> None:
#         # 装備スロット: 防具4種類
#         self._helmet: Optional[UniqueItem] = None
#         self._chest: Optional[UniqueItem] = None  
#         self._gloves: Optional[UniqueItem] = None
#         self._shoes: Optional[UniqueItem] = None
        
#         # 装備可能なアイテムタイプの定義
#         self._slot_types: Dict[str, ItemType] = {
#             "helmet": ItemType.HELMET,
#             "chest": ItemType.CHEST,
#             "gloves": ItemType.GLOVES,
#             "shoes": ItemType.SHOES
#         }
    
#     # ===== プロパティ =====
#     @property
#     def helmet(self) -> Optional[UniqueItem]:
#         """装備中のヘルメットを取得"""
#         return self._helmet
    
#     @property
#     def chest(self) -> Optional[UniqueItem]:
#         """装備中のチェストプレートを取得"""
#         return self._chest
    
#     @property
#     def gloves(self) -> Optional[UniqueItem]:
#         """装備中のグローブを取得"""
#         return self._gloves
    
#     @property
#     def shoes(self) -> Optional[UniqueItem]:
#         """装備中のシューズを取得"""
#         return self._shoes
    
#     # ===== 装備メソッド =====
#     def equip_helmet(self, unique_item: UniqueItem) -> Optional[UniqueItem]:
#         """ヘルメットを装備し、外した装備があれば返す"""
#         if not self._can_equip(unique_item, ItemType.HELMET):
#             raise ValueError(f"ヘルメット以外のアイテムは装備できません: {unique_item.item.name}")
        
#         previous = self._helmet
#         self._helmet = unique_item
#         return previous
    
#     def equip_chest(self, unique_item: UniqueItem) -> Optional[UniqueItem]:
#         """チェストプレートを装備し、外した装備があれば返す"""
#         if not self._can_equip(unique_item, ItemType.CHEST):
#             raise ValueError(f"チェストプレート以外のアイテムは装備できません: {unique_item.item.name}")
        
#         previous = self._chest
#         self._chest = unique_item
#         return previous
    
#     def equip_gloves(self, unique_item: UniqueItem) -> Optional[UniqueItem]:
#         """グローブを装備し、外した装備があれば返す"""
#         if not self._can_equip(unique_item, ItemType.GLOVES):
#             raise ValueError(f"グローブ以外のアイテムは装備できません: {unique_item.item.name}")
        
#         previous = self._gloves
#         self._gloves = unique_item
#         return previous
    
#     def equip_shoes(self, unique_item: UniqueItem) -> Optional[UniqueItem]:
#         """シューズを装備し、外した装備があれば返す"""
#         if not self._can_equip(unique_item, ItemType.SHOES):
#             raise ValueError(f"シューズ以外のアイテムは装備できません: {unique_item.item.name}")
        
#         previous = self._shoes
#         self._shoes = unique_item
#         return previous
    
#     # ===== 脱装メソッド =====
#     def unequip_helmet(self) -> Optional[UniqueItem]:
#         """ヘルメットを脱装し、外した装備を返す"""
#         previous = self._helmet
#         self._helmet = None
#         return previous
    
#     def unequip_chest(self) -> Optional[UniqueItem]:
#         """チェストプレートを脱装し、外した装備を返す"""
#         previous = self._chest
#         self._chest = None
#         return previous
    
#     def unequip_gloves(self) -> Optional[UniqueItem]:
#         """グローブを脱装し、外した装備を返す"""
#         previous = self._gloves
#         self._gloves = None
#         return previous
    
#     def unequip_shoes(self) -> Optional[UniqueItem]:
#         """シューズを脱装し、外した装備を返す"""
#         previous = self._shoes
#         self._shoes = None
#         return previous
    
#     # ===== ボーナス計算 =====
#     def get_attack_bonus(self) -> int:
#         """装備による攻撃力ボーナスを計算"""
#         total = 0
#         for equipment in self._get_all_equipment():
#             if equipment and equipment.attack is not None:
#                 total += equipment.attack
#         return total
    
#     def get_defense_bonus(self) -> int:
#         """装備による防御力ボーナスを計算"""
#         total = 0
#         for equipment in self._get_all_equipment():
#             if equipment and equipment.defense is not None:
#                 total += equipment.defense
#         return total
    
#     def get_speed_bonus(self) -> int:
#         """装備による素早さボーナスを計算"""
#         total = 0
#         for equipment in self._get_all_equipment():
#             if equipment and equipment.speed is not None:
#                 total += equipment.speed
#         return total
    
#     # ===== ユーティリティメソッド =====
#     def get_equipment_display(self) -> str:
#         """装備の表示用文字列を生成"""
#         lines = ["=== 装備 ==="]
        
#         # 各スロットの表示
#         equipment_slots = [
#             ("ヘルメット", self._helmet),
#             ("チェストプレート", self._chest),
#             ("グローブ", self._gloves),
#             ("シューズ", self._shoes)
#         ]
        
#         for slot_name, equipment in equipment_slots:
#             if equipment:
#                 status = "装備不能" if equipment.is_broken() else "装備中"
#                 lines.append(f"• {slot_name}: {equipment.item.name} (耐久度:{equipment.durability}) [{status}]")
#                 bonuses = []
#                 if equipment.attack and equipment.attack > 0:
#                     bonuses.append(f"攻撃+{equipment.attack}")
#                 if equipment.defense and equipment.defense > 0:
#                     bonuses.append(f"防御+{equipment.defense}")
#                 if equipment.speed and equipment.speed > 0:
#                     bonuses.append(f"素早さ+{equipment.speed}")
#                 if bonuses:
#                     lines.append(f"  効果: {', '.join(bonuses)}")
#             else:
#                 lines.append(f"• {slot_name}: なし")
        
#         # 合計ボーナス
#         lines.append("")
#         lines.append(f"合計ボーナス: 攻撃+{self.get_attack_bonus()} 防御+{self.get_defense_bonus()} 素早さ+{self.get_speed_bonus()}")
        
#         return "\n".join(lines)
    
#     def is_empty(self) -> bool:
#         """何も装備していないかどうか"""
#         return all(equipment is None for equipment in self._get_all_equipment())
    
#     def get_equipped_count(self) -> int:
#         """装備している防具の数を取得"""
#         return sum(1 for equipment in self._get_all_equipment() if equipment is not None)
    
#     def has_broken_equipment(self) -> bool:
#         """破損した装備を持っているかどうか"""
#         return any(equipment and equipment.is_broken() for equipment in self._get_all_equipment())
    
#     def get_broken_equipment(self) -> List[UniqueItem]:
#         """破損した装備のリストを取得"""
#         return [equipment for equipment in self._get_all_equipment() 
#                 if equipment and equipment.is_broken()]
    
#     # ===== 内部メソッド =====
#     def _can_equip(self, unique_item: UniqueItem, expected_type: ItemType) -> bool:
#         """アイテムが指定されたタイプで装備可能かチェック"""
#         return unique_item.item.item_type == expected_type and not unique_item.is_broken()
    
#     def _get_all_equipment(self) -> List[Optional[UniqueItem]]:
#         """全ての装備スロットのリストを取得"""
#         return [self._helmet, self._chest, self._gloves, self._shoes]