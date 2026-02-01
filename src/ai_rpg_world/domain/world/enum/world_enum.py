from enum import Enum


class TerrainTypeEnum(Enum):
    """地形の種類"""
    ROAD = "ROAD"
    GRASS = "GRASS"
    BUSH = "BUSH"
    SWAMP = "SWAMP"
    WALL = "WALL"
    WATER = "WATER"


class ObjectTypeEnum(Enum):
    """相互作用オブジェクトの種類"""
    CHEST = "CHEST"
    DOOR = "DOOR"
    GATE = "GATE"
    SIGN = "SIGN"
    SWITCH = "SWITCH"


class SpotCategoryEnum(Enum):
    """スポットのカテゴリ"""
    TOWN = "TOWN"
    VILLAGE = "VILLAGE"
    DUNGEON = "DUNGEON"
    FIELD = "FIELD"
    INN = "INN"
    SHOP = "SHOP"
    QUEST_HUB = "QUEST_HUB"
    SAVE_POINT = "SAVE_POINT"
    OTHER = "OTHER"


class TriggerTypeEnum(Enum):
    """タイルトリガーの種類"""
    WARP = "WARP"
    DAMAGE = "DAMAGE"
    EVENT = "EVENT"
