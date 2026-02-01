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
    PLAYER = "PLAYER"
    NPC = "NPC"


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


class MovementCapabilityEnum(Enum):
    """移動能力の種類"""
    WALK = "WALK"          # 通常の歩行
    SWIM = "SWIM"          # 水泳（水の上を歩ける）
    FLY = "FLY"            # 飛行（進入不可タイル以外を越えられる）
    GHOST_WALK = "GHOST_WALK" # 壁抜け


class DirectionEnum(Enum):
    """向きの種類"""
    NORTH = "NORTH"
    SOUTH = "SOUTH"
    EAST = "EAST"
    WEST = "WEST"
    UP = "UP"
    DOWN = "DOWN"


class BehaviorStateEnum(Enum):
    """アクターの行動状態"""
    IDLE = "IDLE"       # 待機
    PATROL = "PATROL"   # 巡回
    CHASE = "CHASE"     # 追跡
    SEARCH = "SEARCH"   # 探索（見失った地点へ向かう）
    FLEE = "FLEE"       # 逃走
    RETURN = "RETURN"   # 初期位置への帰還
