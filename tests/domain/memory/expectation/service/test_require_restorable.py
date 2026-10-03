"""require_restorable が、Being に戻す予期・未配信の出来事・記憶のターン数の組が食い違うとき、書き込む前に拒む挙動を保証する。"""

from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationValidationException,
)
from ai_rpg_world.domain.memory.expectation.service.require_restorable import (
    require_restorable,
)
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
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
from ai_rpg_world.domain.memory.expectation.value_object.undelivered_expectation_event import (
    UndeliveredExpectationEvent,
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


def _missed_at_11(holder: BeingId = RIO) -> tuple[Expectation, UndeliveredExpectationEvent]:
    expectation = _expectation(holder=holder)
    event = expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
    assert event is not None
    return expectation, UndeliveredExpectationEvent.of(event)


def _call(**overrides: Any) -> None:
    expectation, event = _missed_at_11()
    fields: dict[str, Any] = {
        "expectations": [expectation],
        "undelivered_events": [event],
        "turn": 11,
    }
    fields.update(overrides)
    require_restorable(RIO, **fields)


def test_consistent_set_passes() -> None:
    """持ち主がそろい、出来事の予期があり、ターン数が予期と出来事のターン以上なら通る。"""
    _call()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"expectations": [_expectation(holder=NOA)], "undelivered_events": []}, "being-noa"),
        ({"undelivered_events": [_missed_at_11(NOA)[1]]}, "being-noa"),
        ({"expectations": [_expectation(), _expectation()], "undelivered_events": []}, "appears twice"),
        ({"undelivered_events": [_missed_at_11()[1], _missed_at_11()[1]]}, "appears twice"),
        ({"expectations": [_expectation("exp-9")]}, "no expectation"),
        ({"turn": 10}, "turn"),
        ({"expectations": [_expectation()], "undelivered_events": [], "turn": 9}, "turn"),
        ({"turn": -1}, "turn"),
    ],
    ids=[
        "expectation_of_other_holder",
        "event_of_other_holder",
        "duplicated_expectation",
        "duplicated_event",
        "event_without_expectation",
        "turn_before_event",
        "turn_before_formed",
        "negative_turn",
    ],
)
def test_inconsistent_set_raises(overrides: dict[str, Any], message: str) -> None:
    """別の持ち主・重複・予期の無い出来事・予期や出来事より前のターン数のどれかがあると、ExpectationValidationException で拒む。"""
    with pytest.raises(ExpectationValidationException, match=message):
        _call(**overrides)


def test_turn_before_closed_turn_raises() -> None:
    """期限切れで終わったターンより小さいターン数は ExpectationValidationException で拒む。"""
    expired = _expectation()
    expired.expire_if_overdue(now_turn=25)

    with pytest.raises(ExpectationValidationException, match="turn"):
        require_restorable(RIO, expectations=[expired], undelivered_events=[], turn=24)
