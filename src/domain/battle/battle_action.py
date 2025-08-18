from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict
from src.domain.battle.battle_enum import StatusEffectType, Element, BuffType
from src.domain.monster.monster_enum import Race


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
    damage_multiplier: float = 1.0
    element: Optional[Element] = None
    
    # 回復系
    heal_amount: Optional[int] = None
    
    # 状態異常
    status_effect_rate: Dict[StatusEffectType, float] = field(default_factory=dict)
    status_effect_duration: Dict[StatusEffectType, int] = field(default_factory=dict)
    
    # バフ、デバフ
    buff_multiplier: Dict[BuffType, float] = field(default_factory=dict)
    buff_duration: Dict[BuffType, int] = field(default_factory=dict)
    
    # 種族特攻
    race_attack_multiplier: Dict[Race, float] = field(default_factory=dict)
    
    # コスト
    hp_cost: Optional[int] = None
    mp_cost: Optional[int] = None
    
    # その他
    hit_rate: Optional[float] = None
    
    def __post_init__(self):
        """バリデーション"""
        if self.hit_rate is not None and (self.hit_rate < 0 or self.hit_rate > 1.0):
            raise ValueError(f"hit_rate must be between 0 and 1. hit_rate: {self.hit_rate}")
        if self.mp_cost is not None and self.mp_cost < 0:
            raise ValueError(f"mp_cost must be non-negative. mp_cost: {self.mp_cost}")
        if self.hp_cost is not None and self.hp_cost < 0:
            raise ValueError(f"hp_cost must be non-negative. hp_cost: {self.hp_cost}")
        if self.damage_multiplier < 0:
            raise ValueError(f"damage_multiplier must be non-negative. damage_multiplier: {self.damage_multiplier}")
        for rate in self.status_effect_rate.values():
            if rate < 0 or rate > 1.0:
                raise ValueError(f"status_effect_rate must be between 0 and 1.0. status_effect_rate: {rate}")
        for multiplier in self.race_attack_multiplier.values():
            if multiplier < 0:
                raise ValueError(f"race_attack_multiplier must be non-negative. race_attack_multiplier: {multiplier}")
        for multiplier in self.buff_multiplier.values():
            if multiplier < 0:
                raise ValueError(f"buff_multiplier must be non-negative. buff_multiplier: {multiplier}")