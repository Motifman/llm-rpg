from enum import Enum


class MonsterType(Enum):
    NORMAL = "normal"
    AGGRESSIVE = "aggressive"
    HIDDEN = "hidden"
    PASSIVE = "passive"


class BehaviorPattern(Enum):
    RANDOM_ATTACK = "random_attack"
    DEFENSIVE = "defensive"
    BERSERKER = "berserker"
    TACTICAL = "tactical"