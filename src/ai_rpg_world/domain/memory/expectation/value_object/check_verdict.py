from __future__ import annotations

from enum import Enum


class Outcome(str, Enum):
    """予期の当否。暫定の判定にも確定の判定にもなる。"""

    HIT = "hit"
    MISS = "miss"


class CheckVerdict(str, Enum):
    """照合 1 回ぶんの判定。"""

    HIT = "hit"
    MISS = "miss"
    UNDETERMINED = "undetermined"
    NOT_AN_EXPECTATION = "not_an_expectation"

    @property
    def outcome(self) -> Outcome | None:
        if self is CheckVerdict.HIT:
            return Outcome.HIT
        if self is CheckVerdict.MISS:
            return Outcome.MISS
        return None


__all__ = ["CheckVerdict", "Outcome"]
