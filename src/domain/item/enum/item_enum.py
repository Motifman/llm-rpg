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


class Rarity(Enum):
    """レアリティ（将来のDBスキーマに準拠）"""
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    MYTHIC = "mythic"


