from enum import Enum


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