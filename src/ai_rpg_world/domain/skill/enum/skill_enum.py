from enum import Enum


class DeckTier(Enum):
    NORMAL = "normal"
    AWAKENED = "awakened"


class SkillProposalType(Enum):
    ADD = "add"
    REPLACE = "replace"
    DEGRADE = "degrade"
    FUSE = "fuse"
