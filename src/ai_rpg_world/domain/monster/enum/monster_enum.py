from enum import Enum


class MonsterStatusEnum(Enum):
    """モンスターの状態"""
    ALIVE = "alive"
    DEAD = "dead"
    RESPAWNING = "respawning"


class MonsterFactionEnum(Enum):
    """モンスターの派閥・敵対関係"""
    ENEMY = "enemy"      # 敵対（先制攻撃あり）
    NEUTRAL = "neutral"  # 中立（攻撃されるまで反撃しない）
    ALLY = "ally"        # 友好（プレイヤーの味方）


class DeathCauseEnum(Enum):
    """モンスター死亡原因（LLM・クエスト・報酬判定用）"""
    KILLED_BY_PLAYER = "killed_by_player"
    KILLED_BY_MONSTER = "killed_by_monster"
    STARVATION = "starvation"
    NATURAL = "natural"  # 寿命（Phase 7 用）


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


class ActiveTimeType(Enum):
    """活動時間帯（いつ行動するか）"""
    ALWAYS = "always"       # 常時活動
    DIURNAL = "diurnal"     # 昼行性（昼のみ）
    NOCTURNAL = "nocturnal"  # 夜行性（夜のみ）
    CREPUSCULAR = "crepuscular"  # 薄明性（朝・夕のみ）
