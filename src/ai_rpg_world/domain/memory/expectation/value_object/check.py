from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationValidationException,
)
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
)
from ai_rpg_world.domain.memory.expectation.value_object.turn import require_turn


@dataclass(frozen=True)
class Check:
    """照合 1 回ぶん。本人の何ターン目に、どう判定されたか。"""

    turn: int
    verdict: CheckVerdict

    def __post_init__(self) -> None:
        require_turn(self.turn, name="Check.turn")
        if not isinstance(self.verdict, CheckVerdict):
            raise ExpectationValidationException(
                "Check.verdict must be CheckVerdict"
            )


__all__ = ["Check"]
