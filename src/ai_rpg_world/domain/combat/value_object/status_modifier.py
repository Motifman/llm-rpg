from dataclasses import dataclass
from enum import Enum, auto
from typing import List


class ModifierType(Enum):
    """補正の適用タイプ"""
    ADDITIVE = auto()       # 加算
    MULTIPLICATIVE = auto()  # 乗算


class StatTarget(Enum):
    """補正対象のステータス"""
    MAX_HP = auto()
    MAX_MP = auto()
    ATTACK = auto()
    DEFENSE = auto()
    SPEED = auto()
    CRITICAL_RATE = auto()
    EVASION_RATE = auto()


@dataclass(frozen=True)
class StatusModifier:
    """ステータス補正（バフ・デバフ）を表す値オブジェクト"""
    target: StatTarget
    modifier_type: ModifierType
    value: float  # 加算なら量、乗算なら倍率（例：1.2 = 20%アップ）

    @classmethod
    def attack_up(cls, amount: float, is_multiplier: bool = False) -> "StatusModifier":
        """攻撃力アップのヘルパー"""
        return cls(
            target=StatTarget.ATTACK,
            modifier_type=ModifierType.MULTIPLICATIVE if is_multiplier else ModifierType.ADDITIVE,
            value=amount
        )

    @classmethod
    def defense_up(cls, amount: float, is_multiplier: bool = False) -> "StatusModifier":
        """防御力アップのヘルパー"""
        return cls(
            target=StatTarget.DEFENSE,
            modifier_type=ModifierType.MULTIPLICATIVE if is_multiplier else ModifierType.ADDITIVE,
            value=amount
        )
