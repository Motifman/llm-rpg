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
    # 物理攻撃不能
    BLINDNESS = "blindness"
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


class ActionType(Enum):
    """行動タイプ"""
    MAGIC = "magic"
    PHYSICAL = "physical"
    SPECIAL = "special"


class TargetSelectionMethod(Enum):
    """ターゲット選択方法"""
    SINGLE_TARGET = "single_target"      # 単一ターゲット指定
    ALL_ENEMIES = "all_enemies"          # 敵全体
    ALL_ALLIES = "all_allies"           # 味方全体
    RANDOM_ENEMY = "random_enemy"        # 敵からランダム
    RANDOM_ALLY = "random_ally"          # 味方からランダム
    RANDOM_ALL = "random_all"            # 全員からランダム
    SELF = "self"                       # 自分
    NONE = "none"                       # ターゲットなし


class Race(Enum):
    HUMAN = "human"
    GHOST = "ghost"
    GOBLIN = "goblin"
    ORC = "orc"
    TROLL = "troll"
    TITAN = "titan"
    WEREWOLF = "werewolf"
    WITCH = "witch"
    WIZARD = "wizard"
    WOLF = "wolf"
    ZOMBIE = "zombie"
    DRAGON = "dragon"
    BEAST = "beast"

