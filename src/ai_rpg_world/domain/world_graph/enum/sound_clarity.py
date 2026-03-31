from enum import Enum


class SoundClarityEnum(str, Enum):
    """受信者が聞き取れる明瞭さ"""

    CLEAR = "CLEAR"
    MUFFLED = "MUFFLED"
    FAINT = "FAINT"
