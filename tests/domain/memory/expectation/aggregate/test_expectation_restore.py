"""保存した状態から予期を作り直す Expectation.restore が、状態をそのまま戻し、規則と食い違う状態を拒む挙動を保証する。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationSettled,
)
from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationAlreadyClosedException,
    ExpectationCheckRuleException,
    ExpectationValidationException,
)
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
    Outcome,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_snapshot import (
    ExpectationSnapshot,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_status import (
    ExpectationStatus,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)

HIT = CheckVerdict.HIT
MISS = CheckVerdict.MISS
UNDETERMINED = CheckVerdict.UNDETERMINED
VOID = CheckVerdict.NOT_AN_EXPECTATION
OPEN = ExpectationStatus.OPEN
SETTLED = ExpectationStatus.SETTLED
DISMISSED = ExpectationStatus.DISMISSED
VOIDED = ExpectationStatus.VOIDED
EXPIRED = ExpectationStatus.EXPIRED
FORMED_AT = 10
EXPIRES_AT = 20


def _checks(*pairs: tuple[int, CheckVerdict]) -> tuple[Check, ...]:
    return tuple(Check(turn=turn, verdict=verdict) for turn, verdict in pairs)


def _restore(**overrides: Any) -> Expectation:
    fields: dict[str, Any] = {
        "expectation_id": ExpectationId("exp-1"),
        "holder": BeingId("being-rio"),
        "content": "箱を開けても空だろう",
        "origin": ExpectationOrigin.WITH_ACTION,
        "likelihood": Likelihood.PROBABLY,
        "formed_at_turn": FORMED_AT,
        "expires_at_turn": EXPIRES_AT,
        "beliefs_in_mind": ("belief-1",),
        "shape": None,
        "checks": (),
        "status": OPEN,
        "closed_at_turn": None,
    }
    fields.update(overrides)
    return Expectation.restore(ExpectationSnapshot(**fields))


class TestRestoreOpenExpectation:
    """清算待ちの状態から作り直した予期が、保存前と同じ規則で判定を受け取り続ける挙動を保証する。"""

    def test_restored_hit_settles_with_next_hit(self) -> None:
        """当たったを 1 回持つ清算待ちを作り直すと、次の当たったで確定し、頭にあった信念を出来事で運ぶ。"""
        expectation = _restore(checks=_checks((11, HIT)))

        event = expectation.record(Check(turn=12, verdict=HIT))

        assert event == ExpectationSettled(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=12,
            outcome=Outcome.HIT,
            likelihood=Likelihood.PROBABLY,
            beliefs_in_mind=("belief-1",),
            episodes_in_mind=(),
        )

    def test_restored_miss_then_undetermined_settles_as_miss_when_overdue(
        self,
    ) -> None:
        """外れた → まだ分からない を持つ清算待ちを作り直すと、期限を過ぎたとき外れたで確定する。"""
        expectation = _restore(checks=_checks((11, MISS), (12, UNDETERMINED)))

        event = expectation.expire_if_overdue(now_turn=EXPIRES_AT + 1)

        assert isinstance(event, ExpectationSettled)
        assert event.outcome is Outcome.MISS

    def test_restored_check_turn_still_bounds_next_check(self) -> None:
        """作り直したあとも、保存した最後の照合のターン以前の照合は ExpectationCheckRuleException で拒む。"""
        expectation = _restore(checks=_checks((15, UNDETERMINED)))

        with pytest.raises(ExpectationCheckRuleException, match="previous check"):
            expectation.record(Check(turn=15, verdict=HIT))

    def test_restored_settleable_shape_rejects_second_shape_judgment(self) -> None:
        """形の判定が「清算できる」で済んだ清算待ちを作り直すと、2 回目の形の判定を ExpectationCheckRuleException で拒む。"""
        expectation = _restore(shape=ShapeVerdict.SETTLEABLE)

        with pytest.raises(ExpectationCheckRuleException, match="shape"):
            expectation.judge_shape(ShapeVerdict.OWN_ACTION, turn=11)

    def test_restored_settleable_shape_accepts_checks(self) -> None:
        """形の判定が「清算できる」で済んだ清算待ちを作り直すと、照合を受け取る。"""
        expectation = _restore(shape=ShapeVerdict.SETTLEABLE)

        event = expectation.record(Check(turn=11, verdict=MISS))

        assert event is not None

    def test_restored_keeps_formation_fields(self) -> None:
        """作り直した予期は、予期の文・期日・持ったときの行動・頭にあった信念とエピソードを保持する。"""
        expectation = _restore(
            due="二日後の朝",
            formed_with="ノアに話しかける",
            episodes_in_mind=("episode-9",),
        )

        assert expectation.content == "箱を開けても空だろう"
        assert expectation.due == "二日後の朝"
        assert expectation.formed_with == "ノアに話しかける"
        assert expectation.beliefs_in_mind == ("belief-1",)
        assert expectation.episodes_in_mind == ("episode-9",)


_CLOSED_STATES = {
    "settled_by_two_hits": {
        "checks": _checks((11, HIT), (12, UNDETERMINED), (13, HIT)),
        "status": SETTLED,
        "closed_at_turn": 13,
    },
    "settled_by_expiry": {
        "checks": _checks((11, MISS), (12, UNDETERMINED)),
        "status": SETTLED,
        "closed_at_turn": EXPIRES_AT + 3,
    },
    "voided": {
        "checks": _checks((11, HIT), (12, VOID)),
        "status": VOIDED,
        "closed_at_turn": 12,
    },
    "dismissed": {
        "shape": ShapeVerdict.OWN_ACTION,
        "status": DISMISSED,
        "closed_at_turn": FORMED_AT,
    },
    "expired": {
        "checks": _checks((11, UNDETERMINED)),
        "status": EXPIRED,
        "closed_at_turn": EXPIRES_AT + 1,
    },
}


def _record(expectation: Expectation) -> object:
    return expectation.record(Check(turn=EXPIRES_AT, verdict=MISS))


def _judge_shape(expectation: Expectation) -> object:
    return expectation.judge_shape(ShapeVerdict.SETTLEABLE, turn=EXPIRES_AT)


def _expire(expectation: Expectation) -> object:
    return expectation.expire_if_overdue(now_turn=99)


class TestRestoreClosedExpectation:
    """終わった状態から作り直した予期が、それ以上判定も期限の確認も受け取らない挙動を保証する。"""

    @pytest.mark.parametrize("state", _CLOSED_STATES.values(), ids=_CLOSED_STATES.keys())
    @pytest.mark.parametrize(
        "operate", [_record, _judge_shape, _expire], ids=lambda f: f.__name__
    )
    def test_any_operation_on_restored_closed_expectation_raises(
        self, state: dict[str, Any], operate: Callable[[Expectation], object]
    ) -> None:
        """確定 (2 回続いた / 期限)・予期になっていない・形で外した・期限切れのどれから作り直しても、照合・形の判定・期限の確認を渡すと ExpectationAlreadyClosedException を投げる。"""
        expectation = _restore(**state)

        with pytest.raises(ExpectationAlreadyClosedException):
            operate(expectation)


def _case(match: str, **state: Any) -> Any:
    return pytest.param(state, match)


_INCONSISTENT_STATES = {
    "status_not_enum": _case("status must be", status="open"),
    "shape_not_enum": _case("shape must be", shape="settleable"),
    "checks_not_tuple": _case("checks must be", checks=[Check(turn=11, verdict=HIT)]),
    "check_not_check": _case("checks must be", checks=("hit",)),
    "check_before_formed_turn": _case("outside", checks=_checks((FORMED_AT - 1, HIT))),
    "check_after_expiry_turn": _case("outside", checks=_checks((EXPIRES_AT + 1, HIT))),
    "checks_not_increasing": _case(
        "strictly increasing", checks=_checks((12, HIT), (12, MISS))
    ),
    "negative_closed_at_turn": _case(
        ">= 0", checks=_checks((11, VOID)), status=VOIDED, closed_at_turn=-1
    ),
    "open_with_closed_at_turn": _case("must be set exactly", closed_at_turn=15),
    "closed_without_closed_at_turn": _case(
        "must be set exactly", checks=_checks((11, HIT), (12, HIT)), status=SETTLED
    ),
    "open_already_settled": _case(
        "contradicts", checks=_checks((11, HIT), (12, UNDETERMINED), (13, HIT))
    ),
    "open_with_not_an_expectation": _case("contradicts", checks=_checks((11, VOID))),
    "open_with_unsettleable_shape": _case(
        "contradicts", shape=ShapeVerdict.TRUE_EITHER_WAY
    ),
    "settled_without_outcome": _case(
        "contradicts",
        checks=_checks((11, UNDETERMINED)),
        status=SETTLED,
        closed_at_turn=EXPIRES_AT + 1,
    ),
    "settled_with_not_an_expectation": _case(
        "contradicts", checks=_checks((11, VOID)), status=SETTLED, closed_at_turn=11
    ),
    "settled_by_two_hits_at_other_turn": _case(
        "closed at turn",
        checks=_checks((11, HIT), (12, HIT)),
        status=SETTLED,
        closed_at_turn=15,
    ),
    "checks_continue_after_settlement": _case(
        "must not continue",
        checks=_checks((11, HIT), (12, HIT), (13, MISS)),
        status=SETTLED,
        closed_at_turn=13,
    ),
    "settled_by_expiry_before_overdue": _case(
        "closed at turn",
        checks=_checks((11, HIT)),
        status=SETTLED,
        closed_at_turn=EXPIRES_AT,
    ),
    "voided_without_not_an_expectation": _case(
        "contradicts", checks=_checks((11, HIT)), status=VOIDED, closed_at_turn=11
    ),
    "voided_with_settlement": _case(
        "contradicts",
        checks=_checks((11, HIT), (12, HIT)),
        status=VOIDED,
        closed_at_turn=12,
    ),
    "voided_at_other_turn": _case(
        "closed at turn", checks=_checks((11, VOID)), status=VOIDED, closed_at_turn=12
    ),
    "checks_continue_after_void": _case(
        "must not continue",
        checks=_checks((11, VOID), (12, VOID)),
        status=VOIDED,
        closed_at_turn=12,
    ),
    "dismissed_without_shape": _case(
        "contradicts", status=DISMISSED, closed_at_turn=FORMED_AT
    ),
    "dismissed_with_settleable_shape": _case(
        "contradicts",
        shape=ShapeVerdict.SETTLEABLE,
        status=DISMISSED,
        closed_at_turn=FORMED_AT,
    ),
    "dismissed_with_checks": _case(
        "must not have checks",
        shape=ShapeVerdict.OWN_ACTION,
        checks=_checks((11, UNDETERMINED)),
        status=DISMISSED,
        closed_at_turn=FORMED_AT,
    ),
    "dismissed_before_formed_turn": _case(
        "closed at turn",
        shape=ShapeVerdict.OWN_ACTION,
        status=DISMISSED,
        closed_at_turn=FORMED_AT - 1,
    ),
    "dismissed_after_expiry_turn": _case(
        "closed at turn",
        shape=ShapeVerdict.OWN_ACTION,
        status=DISMISSED,
        closed_at_turn=EXPIRES_AT + 1,
    ),
    "expired_with_outcome": _case(
        "contradicts",
        checks=_checks((11, HIT), (12, UNDETERMINED)),
        status=EXPIRED,
        closed_at_turn=EXPIRES_AT + 1,
    ),
    "expired_with_not_an_expectation": _case(
        "contradicts",
        checks=_checks((11, VOID)),
        status=EXPIRED,
        closed_at_turn=EXPIRES_AT + 1,
    ),
    "expired_before_overdue": _case(
        "closed at turn", status=EXPIRED, closed_at_turn=EXPIRES_AT
    ),
}


class TestRestoreRejectsInconsistentState:
    """保存した状態が清算の規則と食い違うとき、作り直さずに拒む挙動を保証する。"""

    @pytest.mark.parametrize(
        "state, match", _INCONSISTENT_STATES.values(), ids=_INCONSISTENT_STATES.keys()
    )
    def test_inconsistent_state_raises_validation_exception(
        self, state: dict[str, Any], match: str
    ) -> None:
        """型の違う項目、期間の外や順序の崩れた照合、照合の記録と形から導ける終わり方と食い違う状態、終わり方に合わない終わったターンを渡すと、その食い違いを示す ExpectationValidationException を投げる。"""
        with pytest.raises(ExpectationValidationException, match=match):
            _restore(**state)

    def test_invalid_formation_field_raises_validation_exception(self) -> None:
        """作り直すときも、期限のターンが作ったターンより前なら ExpectationValidationException を投げる。"""
        with pytest.raises(ExpectationValidationException, match="expires_at_turn"):
            _restore(expires_at_turn=FORMED_AT - 1)
