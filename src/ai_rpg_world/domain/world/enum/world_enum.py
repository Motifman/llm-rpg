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
    RESOURCE = "RESOURCE"
    GROUND_ITEM = "GROUND_ITEM"  # 落ちているアイテム（当たり判定なし・同一座標に複数可）


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
    """タイル／オブジェクトトリガーの種類"""
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


class EnvironmentTypeEnum(Enum):
    """環境の種類（天候の影響を左右する）"""
    OUTDOOR = "OUTDOOR"      # 屋外（天候の影響をフルに受ける）
    INDOOR = "INDOOR"        # 屋内（天候の影響を受けない）
    UNDERGROUND = "UNDERGROUND" # 地下（天候の影響を受けず、独自の環境変化がある可能性がある）


class BehaviorActionType(Enum):
    """AIが決定したアクションの種類"""
    MOVE = "MOVE"
    USE_SKILL = "USE_SKILL"
    WAIT = "WAIT"


class Disposition(Enum):
    """種族間の関係タイプ（アクターから対象への態度）"""
    NEUTRAL = "neutral"   # 無視（攻撃しない・逃げない・優先しない）
    ALLY = "ally"         # 味方（攻撃しない）
    HOSTILE = "hostile"   # 敵対（攻撃・CHASE の対象）
    PREY = "prey"         # 獲物（敵対かつターゲット選択で優先）
    THREAT = "threat"     # 脅威（視界内にいれば FLEE、攻撃対象にしない）


class InteractionTypeEnum(Enum):
    """インタラクションの種類（拡張時はここに追加）"""
    TALK = "talk"                     # 会話・調べる
    EXAMINE = "examine"                # 調べる
    HARVEST = "harvest"                # 採取・採掘
    MONSTER_FEED = "monster_feed"      # モンスターが食事オブジェクトで採食
    OPEN_CHEST = "open_chest"          # 宝箱を開ける
    OPEN_DOOR = "open_door"            # ドアを開閉
    STORE_IN_CHEST = "store_in_chest"  # 宝箱にアイテムを収納（Command で item 指定）
    TAKE_FROM_CHEST = "take_from_chest"  # 宝箱からアイテムを取得
