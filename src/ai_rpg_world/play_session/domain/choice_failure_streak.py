from __future__ import annotations

from dataclasses import dataclass
from typing import final

# 人を問わず失敗がこの件数続き、この巡りの数にまたがったら止める。健全な run の最長連続は 4、壊れた run の最短は 35 だった
# (design_decisions 214、D2232 の 7 節)
_FAILURES_TO_GIVE_UP = 8
_ROUNDS_TO_GIVE_UP = 2


@final
@dataclass(frozen=True)
class ChoiceFailureStreak:
    reasons: tuple[str, ...] = ()
    rounds: frozenset[int] = frozenset()
    given_up_on: tuple[str, ...] = ()

    def failed(self, reason: str, round_number: int) -> ChoiceFailureStreak:
        reasons = (*self.reasons, reason)
        rounds = self.rounds | {round_number}
        # 一度止めると決めたら、後から選べたターンが届いても止めたままにし、止めたときの理由を残す
        given_up_on = self.given_up_on
        if not given_up_on and len(reasons) >= _FAILURES_TO_GIVE_UP and len(rounds) >= _ROUNDS_TO_GIVE_UP:
            given_up_on = reasons
        return ChoiceFailureStreak(reasons, rounds, given_up_on)

    def broken(self) -> ChoiceFailureStreak:
        return ChoiceFailureStreak(given_up_on=self.given_up_on)
