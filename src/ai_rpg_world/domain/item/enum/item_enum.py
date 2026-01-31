from enum import Enum


class ItemType(Enum):
    """アイテム種別（将来のDBスキーマに準拠）"""
    EQUIPMENT = "equipment"
    CONSUMABLE = "consumable"
    MATERIAL = "material"
    QUEST = "quest"
    OTHER = "other"
    COSMETIC = "cosmetic"
    TOOL = "tool"
    KEY_ITEM = "key_item"


class EquipmentType(Enum):
    """装備種別（装備品のサブタイプ）"""
    WEAPON = "weapon"
    HELMET = "helmet"
    ARMOR = "armor"
    SHIELD = "shield"
    ACCESSORY = "accessory"
    BOOTS = "boots"


class Rarity(Enum):
    """レアリティ（将来のDBスキーマに準拠）"""
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    MYTHIC = "mythic"


