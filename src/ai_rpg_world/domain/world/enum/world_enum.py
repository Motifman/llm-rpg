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


class EnvironmentTypeEnum(Enum):
    """環境の種類（天候の影響を左右する）"""
    OUTDOOR = "OUTDOOR"      # 屋外（天候の影響をフルに受ける）
    INDOOR = "INDOOR"        # 屋内（天候の影響を受けない）
    UNDERGROUND = "UNDERGROUND" # 地下（天候の影響を受けず、独自の環境変化がある可能性がある）


class BehaviorStateEnum(Enum):
    """
    アクターの行動状態。

    主な遷移: 視界内にTHREAT→FLEE; 敵対でFLEEでない→CHASE(またはHP%でFLEE);
    ターゲット見失い→CHASE/ENRAGEはSEARCH, FLEEはRETURN; SEARCH終了→PATROLまたはRETURN;
    縄張り超過→RETURN; RETURN到着→IDLE; 移動失敗max回→RETURN; HP%≤phase→ENRAGE.
    """
    IDLE = "IDLE"       # 待機
    PATROL = "PATROL"   # 巡回
    CHASE = "CHASE"     # 追跡
    SEARCH = "SEARCH"   # 探索（見失った地点へ向かう）
    FLEE = "FLEE"       # 逃走
    RETURN = "RETURN"   # 初期位置への帰還
    ENRAGE = "ENRAGE"   # 怒り（ボス等のフェーズ状態）


class EcologyTypeEnum(Enum):
    """生態・行動タイプ（追跡・逃走・縄張りの振る舞い）"""
    NORMAL = "normal"           # 通常（発見したら追跡・HPで逃走）
    PATROL_ONLY = "patrol_only" # 巡回のみ（発見しても追わない）
    AMBUSH = "ambush"           # 待ち伏せ（初期位置から一定距離までしか追わない）
    FLEE_ONLY = "flee_only"     # 逃走専用（発見したら逃げるのみ）
    TERRITORIAL = "territorial" # 縄張り（初期位置から一定距離を超えたら帰還）


class BehaviorActionType(Enum):
    """AIが決定したアクションの種類"""
    MOVE = "MOVE"
    USE_SKILL = "USE_SKILL"
    WAIT = "WAIT"


class ActiveTimeType(Enum):
    """活動時間帯（いつ行動するか）"""
    ALWAYS = "always"       # 常時活動
    DIURNAL = "diurnal"     # 昼行性（昼のみ）
    NOCTURNAL = "nocturnal"  # 夜行性（夜のみ）
    CREPUSCULAR = "crepuscular"  # 薄明性（朝・夕のみ）


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
