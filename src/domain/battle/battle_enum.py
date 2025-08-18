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
    # 特殊
    CURSE = "curse"


class BuffType(Enum):
    """バフ、デバフ"""
    ATTACK = "attack"
    DEFENSE = "defense"
    SPEED = "speed"    


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


class BattleResultType(Enum):
    """戦闘結果"""
    VICTORY = "victory"
    DEFEAT = "defeat"
    DRAW = "draw"


class BattleState(Enum):
    WAITING = "waiting"        # プレイヤー参加待ち
    IN_PROGRESS = "in_progress"  # 戦闘中
    COMPLETED = "completed"    # 戦闘終了


class ParticipantType(Enum):
    """参加者タイプ"""
    PLAYER = "player"
    MONSTER = "monster"