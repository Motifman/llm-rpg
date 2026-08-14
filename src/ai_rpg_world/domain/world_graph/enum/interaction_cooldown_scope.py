from enum import Enum


class InteractionCooldownScope(str, Enum):
    """interaction の待ち時間を共有する単位。"""

    ACTOR = "actor"
    WORLD = "world"
