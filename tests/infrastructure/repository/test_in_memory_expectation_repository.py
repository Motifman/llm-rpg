"""InMemoryExpectationRepository が、予期と未配信の出来事と記憶のターン数を Being ごとに同じ保存の単位で持つ挙動を保証する。"""

from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationSettled,
    ProvisionallyMissed,
)
from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationEventNotFoundException,
    ExpectationValidationException,
)
from ai_rpg_world.domain.memory.expectation.repository.memory_turn_reader import (
    MemoryTurnReader,
)
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_grounds import (
    ExpectationGrounds,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)
from ai_rpg_world.domain.memory.expectation.value_object.undelivered_expectation_event import (
    UndeliveredExpectationEvent,
)
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (
    InMemoryExpectationRepository,
)

RIO = BeingId("being-rio")
NOA = BeingId("being-noa")


def _expectation(expectation_id: str = "exp-1", holder: BeingId = RIO) -> Expectation:
    return Expectation(
        expectation_id=ExpectationId(expectation_id),
        holder=holder,
        content="箱を開けても空だろう",
        origin=ExpectationOrigin.WITH_ACTION,
        likelihood=Likelihood.PROBABLY,
        formed_at_turn=10,
        expires_at_turn=20,
    )


def _ids(expectations: list[Expectation]) -> list[str]:
    return [e.expectation_id.value for e in expectations]


class TestOpenExpectations:
    """清算待ちの一覧が、Being ごとに、確定していない予期だけを返す挙動を保証する。"""

    def test_saved_expectation_is_listed_as_open_for_its_holder(self) -> None:
        """保存した予期は、同じ Being の清算待ちの一覧に出る。"""
        repo = InMemoryExpectationRepository()

        repo.save(_expectation(), [])

        assert _ids(repo.list_open_by_being(RIO)) == ["exp-1"]

    def test_settled_expectation_is_not_listed_as_open(self) -> None:
        """当たったが 2 回続いて確定した予期を保存し直すと、清算待ちの一覧に出ない。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()
        repo.save(expectation, [])
        expectation.record(Check(turn=11, verdict=CheckVerdict.HIT))
        settled = expectation.record(Check(turn=12, verdict=CheckVerdict.HIT))

        repo.save(expectation, [settled])

        assert repo.list_open_by_being(RIO) == []

    def test_expectation_of_other_being_is_not_listed(self) -> None:
        """別の Being の予期は、清算待ちの一覧に出ない。"""
        repo = InMemoryExpectationRepository()

        repo.save(_expectation("exp-noa", holder=NOA), [])

        assert repo.list_open_by_being(RIO) == []
        assert _ids(repo.list_open_by_being(NOA)) == ["exp-noa"]

    def test_change_without_save_is_not_stored(self) -> None:
        """一覧から取り出した予期に判定を渡しても、保存し直すまで保存先の状態は変わらない。"""
        repo = InMemoryExpectationRepository()
        repo.save(_expectation(), [])
        (listed,) = repo.list_open_by_being(RIO)
        listed.record(Check(turn=11, verdict=CheckVerdict.HIT))
        listed.record(Check(turn=12, verdict=CheckVerdict.HIT))

        (stored,) = repo.list_open_by_being(RIO)

        assert stored.snapshot().checks == ()


class TestClosingRequiresItsEvent:
    """予期が終わった状態を保存するとき、終わりを告げた出来事を必ず一緒に受け取る挙動を保証する。確定の出来事を失わないため。"""

    def test_closing_without_event_is_rejected_without_storing(self) -> None:
        """清算待ちだった予期を、確定させたのに出来事を渡さず保存すると ExpectationValidationException を投げ、清算待ちのまま残す。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()
        repo.save(expectation, [])
        expectation.record(Check(turn=11, verdict=CheckVerdict.HIT))
        expectation.record(Check(turn=12, verdict=CheckVerdict.HIT))

        with pytest.raises(ExpectationValidationException, match="closed at turn 12"):
            repo.save(expectation, [])

        assert _ids(repo.list_open_by_being(RIO)) == ["exp-1"]

    def test_closing_with_only_provisional_event_is_rejected(self) -> None:
        """確定させた予期を、前のターンの暫定の出来事だけと一緒に保存すると ExpectationValidationException を投げる。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()
        missed = expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        expectation.record(Check(turn=12, verdict=CheckVerdict.MISS))

        with pytest.raises(ExpectationValidationException, match="closed at turn 12"):
            repo.save(expectation, [missed])

        assert repo.list_all_by_being(RIO) == []

    def test_saving_already_closed_expectation_again_needs_no_event(self) -> None:
        """終わった状態で保存済みの予期は、出来事なしで保存し直しても受け付ける。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()
        expired = expectation.expire_if_overdue(now_turn=21)
        repo.save(expectation, [expired])

        repo.save(expectation, [])

        assert len(repo.list_undelivered_by_being(RIO)) == 1

    @pytest.mark.parametrize(
        "close",
        [
            lambda e: e.judge_shape(ShapeVerdict.OWN_ACTION, turn=10, grounds=ExpectationGrounds()),
            lambda e: e.record(Check(turn=11, verdict=CheckVerdict.NOT_AN_EXPECTATION)),
            lambda e: e.expire_if_overdue(now_turn=21),
        ],
        ids=["dismissed", "voided", "expired"],
    )
    def test_every_closed_expectation_is_not_listed_as_open(self, close: Any) -> None:
        """形で外した・予期になっていない・期限切れのどの終わり方も、出来事と一緒に保存すると清算待ちの一覧に出ない。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()

        repo.save(expectation, [close(expectation)])

        assert repo.list_open_by_being(RIO) == []
        assert _ids(repo.list_all_by_being(RIO)) == ["exp-1"]


class TestMemoryTurn:
    """記憶のターン数が Being ごとに 0 から 1 手ずつ進む挙動を保証する。"""

    def test_turn_starts_at_zero(self) -> None:
        """一度も手を受け取っていない Being のターン数は 0。"""
        repo = InMemoryExpectationRepository()

        assert repo.current_turn(RIO) == 0

    def test_each_advance_moves_turn_by_one(self) -> None:
        """1 手を受け取るたびにターン数が 1 進み、進めたあとの値を返す。"""
        repo = InMemoryExpectationRepository()

        advanced = [repo.advance_turn(RIO) for _ in range(3)]

        assert advanced == [1, 2, 3]
        assert repo.current_turn(RIO) == 3

    def test_turn_is_counted_per_being(self) -> None:
        """ある Being の手は、別の Being のターン数を進めない。"""
        repo = InMemoryExpectationRepository()

        repo.advance_turn(RIO)

        assert repo.current_turn(NOA) == 0

    def test_turn_can_be_read_through_memory_turn_reader(self) -> None:
        """予期の保存先は MemoryTurnReader として渡せ、その口から進めたあとのターン数が読める。"""
        repo = InMemoryExpectationRepository()
        repo.advance_turn(RIO)
        repo.advance_turn(RIO)

        reader: MemoryTurnReader = repo

        assert isinstance(reader, MemoryTurnReader)
        assert reader.current_turn(RIO) == 2


class TestUndeliveredEvents:
    """予期の集約が返した出来事を、ID 付きの未配信として予期と同じ保存の単位で残す挙動を保証する。"""

    def test_settled_event_is_stored_as_undelivered_with_id(self) -> None:
        """予期が確定すると、確定の出来事が予期のIDとターンから作った ID 付きの未配信として保存される。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()
        expectation.record(Check(turn=11, verdict=CheckVerdict.HIT))
        settled = expectation.record(Check(turn=12, verdict=CheckVerdict.HIT))
        assert isinstance(settled, ExpectationSettled)

        repo.save(expectation, [settled])

        assert repo.list_undelivered_by_being(RIO) == [
            UndeliveredExpectationEvent(
                event_id=ExpectationEventId("exp-1@12"), event=settled
            )
        ]

    def test_events_accumulate_in_saved_order(self) -> None:
        """保存のたびに渡した出来事は、前の未配信を消さずに保存した順に積まれる。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()
        missed = expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        repo.save(expectation, [missed])
        settled = expectation.record(Check(turn=12, verdict=CheckVerdict.MISS))

        repo.save(expectation, [settled])

        assert [u.event for u in repo.list_undelivered_by_being(RIO)] == [
            missed,
            settled,
        ]

    def test_delivered_event_is_not_listed_as_undelivered(self) -> None:
        """配信済みの印を付けた出来事は、未配信の一覧に出ない。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()
        missed = expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        repo.save(expectation, [missed])

        repo.mark_delivered(RIO, ExpectationEventId("exp-1@11"))

        assert repo.list_undelivered_by_being(RIO) == []

    def test_marking_event_of_other_being_raises(self) -> None:
        """別の Being の未配信の ID に印を付けると ExpectationEventNotFoundException を投げ、その出来事は未配信のまま残る。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()
        missed = expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        repo.save(expectation, [missed])

        with pytest.raises(ExpectationEventNotFoundException):
            repo.mark_delivered(NOA, ExpectationEventId("exp-1@11"))

        assert len(repo.list_undelivered_by_being(RIO)) == 1

    def test_marking_unknown_event_raises(self) -> None:
        """未配信に無い ID に印を付けると ExpectationEventNotFoundException を投げる。"""
        repo = InMemoryExpectationRepository()

        with pytest.raises(ExpectationEventNotFoundException, match="exp-1@11"):
            repo.mark_delivered(RIO, ExpectationEventId("exp-1@11"))

    def test_event_of_other_expectation_is_rejected_without_storing_anything(
        self,
    ) -> None:
        """別の予期の出来事を渡すと ExpectationValidationException を投げ、予期の状態も出来事も保存しない。"""
        repo = InMemoryExpectationRepository()
        repo.save(_expectation(), [])
        expectation = _expectation()
        expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        foreign = ProvisionallyMissed(
            expectation_id=ExpectationId("exp-2"),
            holder=RIO,
            turn=11,
            likelihood=Likelihood.PROBABLY,
        )

        with pytest.raises(ExpectationValidationException, match="exp-2"):
            repo.save(expectation, [foreign])

        (stored,) = repo.list_open_by_being(RIO)
        assert stored.snapshot().checks == ()
        assert repo.list_undelivered_by_being(RIO) == []

    def test_same_event_saved_twice_is_rejected(self) -> None:
        """未配信のまま同じ出来事をもう一度保存すると ExpectationValidationException を投げ、二重には積まない。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()
        missed = expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        repo.save(expectation, [missed])

        with pytest.raises(ExpectationValidationException, match="exp-1@11"):
            repo.save(expectation, [missed])

        assert len(repo.list_undelivered_by_being(RIO)) == 1


class TestReplaceAllByBeing:
    """snapshot の復元で、Being の予期・未配信の出来事・ターン数をまとめて置き換える挙動を保証する。"""

    def test_replace_overwrites_previous_state(self) -> None:
        """置き換えると、それまでの予期と未配信の出来事とターン数は残らない。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()
        missed = expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        repo.save(expectation, [missed])
        repo.advance_turn(RIO)

        repo.replace_all_by_being(
            RIO,
            expectations=[_expectation("exp-9")],
            undelivered_events=[],
            turn=17,
        )

        assert _ids(repo.list_all_by_being(RIO)) == ["exp-9"]
        assert repo.list_undelivered_by_being(RIO) == []
        assert repo.current_turn(RIO) == 17

    def test_failed_replace_keeps_previous_state(self) -> None:
        """別の Being が持つ予期で置き換えようとすると ExpectationValidationException を投げ、それまでの予期・未配信の出来事・ターン数をそのまま残す。"""
        repo = InMemoryExpectationRepository()
        expectation = _expectation()
        missed = expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        repo.save(expectation, [missed])
        repo.advance_turn(RIO)

        with pytest.raises(ExpectationValidationException, match="being-noa"):
            repo.replace_all_by_being(
                RIO,
                expectations=[_expectation(holder=NOA)],
                undelivered_events=[],
                turn=15,
            )

        assert [e.snapshot() for e in repo.list_all_by_being(RIO)] == [
            expectation.snapshot()
        ]
        assert [u.event for u in repo.list_undelivered_by_being(RIO)] == [missed]
        assert repo.current_turn(RIO) == 1

    def test_replace_with_negative_turn_raises(self) -> None:
        """負のターン数で置き換えようとすると ExpectationValidationException を投げる。"""
        repo = InMemoryExpectationRepository()

        with pytest.raises(ExpectationValidationException, match="turn"):
            repo.replace_all_by_being(
                RIO, expectations=[], undelivered_events=[], turn=-1
            )
