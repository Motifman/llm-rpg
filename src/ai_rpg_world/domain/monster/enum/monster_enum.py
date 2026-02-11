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
