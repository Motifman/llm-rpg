from enum import Enum


class DeckTier(Enum):
    NORMAL = "normal"
    AWAKENED = "awakened"


class SkillHitPatternType(Enum):
    MELEE = "melee"
    CONE = "cone"
    AROUND = "around"
    PROJECTILE = "projectile"
    BEAM = "beam"
    SEQUENCE = "sequence"


class SkillProposalType(Enum):
    ADD = "add"
    REPLACE = "replace"
    DEGRADE = "degrade"
    FUSE = "fuse"

