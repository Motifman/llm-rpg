from enum import Enum


class InteractionActorPlane(str, Enum):
    """interaction を実行できる主体の存在層。"""

    LIVING = "LIVING"
    DEPARTED = "DEPARTED"


__all__ = ["InteractionActorPlane"]
