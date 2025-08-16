from enum import Enum
from dataclasses import dataclass
from typing import Optional
from src.domain.battle.battle_enum import StatusEffectType, Element


class ActionType(Enum):
    """行動タイプ"""
    ATTACK = "attack"
    MAGIC = "magic"
    DEFEND = "defend"
    ITEM = "item"
    ESCAPE = "escape"
    STATUS_EFFECT = "status_effect"


@dataclass(frozen=True)
class BattleAction:
    """戦闘行動"""
    action_id: int
    name: str
    description: str
    action_type: ActionType
    
    # ダメージ系
    damage: int = 0
    element: Optional[Element] = None
    
    # ステータス系
    status_effect_type: Optional[StatusEffectType] = None
    status_effect_duration: int = 0
    status_effect_value: int = 0
    
    # コスト
    mp_cost: int = 0
    
    # その他
    hit_rate: float = 1.0
    critical_rate: float = 0.05
    
    def __post_init__(self):
        """バリデーション"""
        assert 0 <= self.hit_rate <= 1.0, "hit_rate must be between 0 and 1"
        assert 0 <= self.critical_rate <= 1.0, "critical_rate must be between 0 and 1"
        assert self.mp_cost >= 0, "mp_cost must be non-negative"
        assert self.damage >= 0, "damage must be non-negative"
        assert self.status_effect_duration >= 0, "status_effect_duration must be non-negative"
