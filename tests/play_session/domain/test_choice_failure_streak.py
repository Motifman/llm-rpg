from __future__ import annotations

from ai_rpg_world.play_session.domain.choice_failure_streak import ChoiceFailureStreak


def _failed(streak: ChoiceFailureStreak, count: int, round_number: int) -> ChoiceFailureStreak:
    for i in range(count):
        streak = streak.failed(f"Timeout: {round_number}-{i}", round_number)
    return streak


class TestChoiceFailureStreak:
    """ChoiceFailureStreak が、人を問わない失敗が 8 件続き 2 巡りにまたがったら止めると決め、その理由を残すことを保証する。"""

    def test_gives_up_on_the_eighth_failure_across_two_rounds(self) -> None:
        """巡り 1 で 4 件、巡り 2 で 3 件の時点では止めず、巡り 2 の 4 件目で、8 件の理由を起きた順に残して止める。"""
        seven = _failed(_failed(ChoiceFailureStreak(), 4, 1), 3, 2)

        eight = seven.failed("Timeout: last", 2)

        assert seven.given_up_on == ()
        assert eight.given_up_on == (*seven.reasons, "Timeout: last")

    def test_eight_failures_in_one_round_do_not_give_up(self) -> None:
        """8 件が 1 つの巡りに収まっていれば、止めない。"""
        assert _failed(ChoiceFailureStreak(), 8, 1).given_up_on == ()

    def test_breaking_forgets_the_failures_and_their_rounds(self) -> None:
        """7 件のあとで続きが切れると、そのあと巡り 3 で 8 件続いても、巡りが 1 つなので止めない。"""
        broken = _failed(_failed(ChoiceFailureStreak(), 4, 1), 3, 2).broken()

        assert _failed(broken, 8, 3).given_up_on == ()

    def test_giving_up_is_kept_after_breaking_and_further_failures(self) -> None:
        """一度止めると決めたら、続きが切れても、そのあとまた失敗しても、止めたときの 8 件の理由のまま変わらない。"""
        given_up = _failed(_failed(ChoiceFailureStreak(), 4, 1), 4, 2)

        later = _failed(_failed(given_up.broken(), 4, 3), 4, 4)

        assert later.given_up_on == given_up.given_up_on
