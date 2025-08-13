from enum import Enum


class ItemType(Enum):
    """アイテム種別（将来のDBスキーマに準拠）"""
    WEAPON = "weapon"
    HELMET = "helmet"
    CHEST = "chest"
    LEGS = "legs"
    BOOTS = "boots"
    GLOVES = "gloves"
    CONSUMABLE = "consumable"
    MATERIAL = "material"
    QUEST = "quest"
    OTHER = "other"


class Rarity(Enum):
    """レアリティ（将来のDBスキーマに準拠）"""
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    MYTHIC = "mythic"


