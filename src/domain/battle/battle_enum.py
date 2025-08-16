from enum import Enum


class StatusEffectType(Enum):
    """状態異常"""
    # ダメージを受ける
    POISON = "poison"    
    BURN = "burn"
    # 回復
    BLESSING = "blessing"
    # 行動不能
    PARALYSIS = "paralysis" 
    SLEEP = "sleep"     
    CONFUSION = "confusion" 
    # 魔法攻撃不能
    SILENCE = "silence" 
    # ステータスアップ
    ATTACK_UP = "attack_up"
    DEFENSE_UP = "defense_up"
    SPEED_UP = "speed_up"    
    # ステータスダウン
    ATTACK_DOWN = "attack_down"
    DEFENSE_DOWN = "defense_down"
    SPEED_DOWN = "speed_down"
    # 特殊
    CURSE = "curse"


class Element(Enum):
    """属性"""
    FIRE = "fire"
    WATER = "water"
    THUNDER = "thunder"
    WIND = "wind"
    ICE = "ice"
    EARTH = "earth"
    GRASS = "grass"
    LIGHT = "light"
    DARKNESS = "darkness"
    NEUTRAL = "neutral"
    POISON = "poison"