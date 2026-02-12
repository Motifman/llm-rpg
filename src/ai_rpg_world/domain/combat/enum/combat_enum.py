from enum import Enum


class StatusEffectType(Enum):
    """ステータス異常・強化の種類"""
    ATTACK_UP = "attack_up"
    ATTACK_DOWN = "attack_down"
    DEFENSE_UP = "defense_up"
    DEFENSE_DOWN = "defense_down"
    SPEED_UP = "speed_up"
    SPEED_DOWN = "speed_down"
    REGENERATION = "regeneration"
    POISON = "poison"
    PARALYSIS = "poison" # 移動不可など
    STUN = "stun" # 行動不可
