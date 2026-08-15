from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExertionKind(Enum):
    TRAVEL_LEG = "travel_leg"
    ATTACK = "attack"
    INTERACT = "interact"
    WAIT = "wait"


@dataclass(frozen=True)
class FatigueExertionPolicy:
    """行為種別ごとの疲労増減と、限界時に止める種別。

    ツール名は知らない。application がツール名を ExertionKind に写す。
    """

    cost_travel_leg: int = 1
    cost_attack: int = 5
    cost_interact: int = 2
    recovery_wait: int = 20

    def cost_of(self, kind: ExertionKind) -> int:
        if kind is ExertionKind.TRAVEL_LEG:
            return self.cost_travel_leg
        if kind is ExertionKind.ATTACK:
            return self.cost_attack
        if kind is ExertionKind.INTERACT:
            return self.cost_interact
        if kind is ExertionKind.WAIT:
            return 0
        raise AssertionError(f"unhandled ExertionKind: {kind!r}")

    def recovery_of(self, kind: ExertionKind) -> int:
        if kind is ExertionKind.WAIT:
            return self.recovery_wait
        return 0

    def is_blocked_when_exhausted(self, kind: ExertionKind) -> bool:
        return kind in (
            ExertionKind.TRAVEL_LEG,
            ExertionKind.ATTACK,
            ExertionKind.INTERACT,
        )


DEFAULT_FATIGUE_EXERTION_POLICY = FatigueExertionPolicy()
