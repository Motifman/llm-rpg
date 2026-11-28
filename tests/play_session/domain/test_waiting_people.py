from __future__ import annotations

from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.play_session.domain.turn_skip import TurnSkipReason
from ai_rpg_world.play_session.domain.waiting_people import WaitingPeople

_MIO, _GEN = PersonId("mio"), PersonId("gen")


class TestWaitingPeople:
    """WaitingPeople が、待っている人ごとに待つ理由を覚え、呼びかけか決めた巡りの数で起こすことを保証する。"""

    def test_each_person_keeps_the_reason_for_waiting(self) -> None:
        """ゲンは待つを選び、ミオは失敗が続いて待ちに入ると、それぞれの理由で答え、待っていない人には None を返す。"""
        waiting = (
            WaitingPeople()
            .started(_GEN, 1, TurnSkipReason.WAITING)
            .started(_MIO, 1, TurnSkipReason.WAITING_AFTER_CHOICES_KEPT_FAILING)
        )

        assert waiting.reason_of(_GEN) is TurnSkipReason.WAITING
        assert waiting.reason_of(_MIO) is TurnSkipReason.WAITING_AFTER_CHOICES_KEPT_FAILING
        assert waiting.reason_of(PersonId("haru")) is None

    def test_waking_by_a_call_wakes_only_that_person(self) -> None:
        """ゲンだけを呼びかけで起こすと、ミオは待ったまま残る。"""
        waiting = (
            WaitingPeople()
            .started(_GEN, 1, TurnSkipReason.WAITING)
            .started(_MIO, 1, TurnSkipReason.WAITING)
            .woken(_GEN)
        )

        assert waiting.reason_of(_GEN) is None
        assert waiting.reason_of(_MIO) is TurnSkipReason.WAITING

    def test_wakes_after_waiting_longer_than_the_set_rounds(self) -> None:
        """巡り 1 で待ち始めたゲンは、3 巡り待つ決まりのとき、巡り 4 ではまだ待ち、巡り 5 で起きる。"""
        waiting = WaitingPeople().started(_GEN, 1, TurnSkipReason.WAITING)

        assert waiting.woken_after(4, 3).reason_of(_GEN) is TurnSkipReason.WAITING
        assert waiting.woken_after(5, 3).reason_of(_GEN) is None
