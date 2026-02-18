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
