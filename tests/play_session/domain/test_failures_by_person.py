from __future__ import annotations

from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.play_session.domain.failures_by_person import FailuresByPerson

_MIO, _GEN = PersonId("mio"), PersonId("gen")


class TestFailuresByPerson:
    """FailuresByPerson が、人ごとに続けて選べなかった数を数え、3 回目で待たせる頃合いだと答えることを保証する。"""

    def test_three_failures_of_the_same_person_are_enough_to_wait(self) -> None:
        """ミオが 2 回続けて選べなかった時点では待たせず、3 回目で待たせる頃合いになる。"""
        twice = FailuresByPerson().failed(_MIO).failed(_MIO)

        thrice = twice.failed(_MIO)

        assert twice.has_failed_enough_to_wait(_MIO) is False
        assert thrice.has_failed_enough_to_wait(_MIO) is True

    def test_failures_are_counted_per_person(self) -> None:
        """ミオとゲンが交互に計 4 回選べなくても、それぞれ 2 回なので、どちらも待たせない。"""
        failures = FailuresByPerson().failed(_MIO).failed(_GEN).failed(_MIO).failed(_GEN)

        assert failures.has_failed_enough_to_wait(_MIO) is False
        assert failures.has_failed_enough_to_wait(_GEN) is False

    def test_clearing_starts_the_count_of_that_person_over(self) -> None:
        """ミオの数を消すと、そのあと 2 回選べなくても待たせず、ゲンの数は残る。"""
        failures = FailuresByPerson().failed(_MIO).failed(_MIO).failed(_GEN).failed(_GEN).cleared(_MIO)

        failures = failures.failed(_MIO).failed(_MIO).failed(_GEN)

        assert failures.has_failed_enough_to_wait(_MIO) is False
        assert failures.has_failed_enough_to_wait(_GEN) is True
