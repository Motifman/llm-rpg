"""予期 (Expectation) が照合・形の判定・期限を受けて状態を移す規則を、返す出来事と例外で保証する。

集約は判定の状態を公開しないので、清算待ちかどうかは「次の判定を受け取れるか」、
暫定の判定は「期限を過ぎたときにどの当否で確定するか」で確かめる。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationDismissed,
    ExpectationExpired,
    ExpectationSettled,
    ExpectationVoided,
    ProvisionallyMissed,
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
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)

HIT = CheckVerdict.HIT
MISS = CheckVerdict.MISS
UNDETERMINED = CheckVerdict.UNDETERMINED
EXPIRES_AT = 20


def _expectation(**overrides: Any) -> Expectation:
    fields: dict[str, Any] = {
        "expectation_id": ExpectationId("exp-1"),
        "holder": BeingId("being-rio"),
        "content": "箱を開けても空だろう",
        "origin": ExpectationOrigin.WITH_ACTION,
        "likelihood": Likelihood.PROBABLY,
        "formed_at_turn": 10,
        "expires_at_turn": EXPIRES_AT,
    }
    fields.update(overrides)
    return Expectation(**fields)


def _record_all(expectation: Expectation, *checks: Check) -> list[object]:
    return [expectation.record(check) for check in checks]


def _outcome_when_overdue(expectation: Expectation) -> Outcome | None:
    """期限を過ぎたときにどの当否で確定するか。期限切れなら None。"""
    event = expectation.expire_if_overdue(now_turn=EXPIRES_AT + 1)
    if isinstance(event, ExpectationSettled):
        return event.outcome
    assert isinstance(event, ExpectationExpired)
    return None


def _assert_closed(expectation: Expectation) -> None:
    with pytest.raises(ExpectationAlreadyClosedException):
        expectation.record(Check(turn=EXPIRES_AT, verdict=HIT))


class TestFormation:
    """予期を作るときに、持ったときの文脈を保持し、時刻の矛盾や不正な項目を拒む挙動を保証する。"""

    def test_new_expectation_expires_when_overdue_without_checks(self) -> None:
        """作ったばかりの予期は清算待ちで暫定の判定を持たないので、照合されないまま期限を過ぎると期限切れになる。"""
        expectation = _expectation()

        event = expectation.expire_if_overdue(now_turn=EXPIRES_AT + 1)

        assert event == ExpectationExpired(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=EXPIRES_AT + 1,
        )

    def test_keeps_texts_and_context_in_mind_at_formation(self) -> None:
        """予期の文・期日・持ったときの行動は文のまま、頭にあった信念とエピソードの ID は渡した順に保持する。"""
        expectation = _expectation(
            origin=ExpectationOrigin.PROMISE_OR_OUTLOOK,
            formed_with="ノアに話しかける",
            due="二日後の朝",
            beliefs_in_mind=("belief-1", "belief-2"),
            episodes_in_mind=("episode-9",),
        )

        assert expectation.content == "箱を開けても空だろう"
        assert expectation.formed_with == "ノアに話しかける"
        assert expectation.due == "二日後の朝"
        assert expectation.beliefs_in_mind == ("belief-1", "belief-2")
        assert expectation.episodes_in_mind == ("episode-9",)

    def test_strips_surrounding_whitespace_of_texts(self) -> None:
        """予期の文と ID の前後の空白は落として保持する。"""
        expectation = _expectation(
            content="  箱は空だろう ", beliefs_in_mind=(" belief-1 ",)
        )

        assert expectation.content == "箱は空だろう"
        assert expectation.beliefs_in_mind == ("belief-1",)

    def test_expiry_turn_before_formed_turn_raises(self) -> None:
        """期限のターンが作ったターンより前なら ExpectationValidationException を投げる。"""
        with pytest.raises(ExpectationValidationException, match="expires_at_turn"):
            _expectation(formed_at_turn=10, expires_at_turn=9)

    def test_expiry_turn_equal_to_formed_turn_is_allowed(self) -> None:
        """期限のターンが作ったターンと同じなら作れ、そのターンの照合を受け取る。"""
        expectation = _expectation(formed_at_turn=10, expires_at_turn=10)

        event = expectation.record(Check(turn=10, verdict=MISS))

        assert isinstance(event, ProvisionallyMissed)

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param({"expectation_id": "exp-1"}, id="id_not_value_object"),
            pytest.param({"holder": "being-rio"}, id="holder_not_being_id"),
            pytest.param({"content": "   "}, id="blank_content"),
            pytest.param({"formed_at_turn": -1}, id="negative_formed_turn"),
            pytest.param({"formed_at_turn": True}, id="bool_formed_turn"),
            pytest.param({"expires_at_turn": "20"}, id="str_expires_turn"),
            pytest.param({"formed_with": ""}, id="blank_formed_with"),
            pytest.param({"due": " "}, id="blank_due"),
            pytest.param({"beliefs_in_mind": ("",)}, id="blank_belief_id"),
            pytest.param({"beliefs_in_mind": (1,)}, id="non_str_belief_id"),
            pytest.param({"episodes_in_mind": ["episode-1"]}, id="episodes_not_tuple"),
            pytest.param({"origin": "with_action"}, id="origin_not_enum"),
            pytest.param({"likelihood": "probably"}, id="likelihood_not_enum"),
        ],
    )
    def test_invalid_field_raises_validation_exception(
        self, overrides: dict[str, Any]
    ) -> None:
        """空の文、負や bool のターン、値オブジェクトや enum でない項目を渡すと ExpectationValidationException を投げる。"""
        with pytest.raises(ExpectationValidationException):
            _expectation(**overrides)


class TestRecordCheck:
    """照合の判定を 1 件ずつ受け取り、暫定と確定のあいだを移る規則を保証する。"""

    def test_undetermined_checks_keep_expectation_open_without_events(self) -> None:
        """まだ分からないが続くあいだは出来事を返さず、清算待ちのまま、期限を過ぎると期限切れになる。"""
        expectation = _expectation()

        events = _record_all(
            expectation,
            Check(turn=11, verdict=UNDETERMINED),
            Check(turn=12, verdict=UNDETERMINED),
            Check(turn=13, verdict=UNDETERMINED),
        )

        assert events == [None, None, None]
        assert _outcome_when_overdue(expectation) is None

    def test_two_consecutive_hits_settle_and_emit_settled_once(self) -> None:
        """当たったが 2 回続くと当たったで確定し、確定の出来事は 2 回目にだけ返し、以後は判定を受け取らない。"""
        expectation = _expectation(
            beliefs_in_mind=("belief-1",), episodes_in_mind=("episode-9",)
        )

        events = _record_all(
            expectation, Check(turn=11, verdict=HIT), Check(turn=12, verdict=HIT)
        )

        assert events == [
            None,
            ExpectationSettled(
                expectation_id=ExpectationId("exp-1"),
                holder=BeingId("being-rio"),
                turn=12,
                outcome=Outcome.HIT,
                likelihood=Likelihood.PROBABLY,
                beliefs_in_mind=("belief-1",),
                episodes_in_mind=("episode-9",),
            ),
        ]
        _assert_closed(expectation)

    def test_miss_then_hit_stays_provisional_and_reports_first_miss(self) -> None:
        """外れた → 当たった と変わったときは確定せず、1 回目の外れで暫定の出来事を返し、暫定の判定は当たったになる。"""
        expectation = _expectation(likelihood=Likelihood.ALMOST_CERTAIN)

        events = _record_all(
            expectation, Check(turn=11, verdict=MISS), Check(turn=12, verdict=HIT)
        )

        assert events == [
            ProvisionallyMissed(
                expectation_id=ExpectationId("exp-1"),
                holder=BeingId("being-rio"),
                turn=11,
                likelihood=Likelihood.ALMOST_CERTAIN,
            ),
            None,
        ]
        assert _outcome_when_overdue(expectation) is Outcome.HIT

    def test_two_consecutive_misses_settle_as_miss_without_second_provisional_event(
        self,
    ) -> None:
        """外れたが 2 回続くと外れたで確定し、2 回目は暫定ではなく確定の出来事だけを返す。"""
        expectation = _expectation()

        events = _record_all(
            expectation, Check(turn=11, verdict=MISS), Check(turn=12, verdict=MISS)
        )

        assert isinstance(events[0], ProvisionallyMissed)
        assert isinstance(events[1], ExpectationSettled)
        assert events[1].outcome is Outcome.MISS

    def test_undetermined_between_same_outcomes_still_settles(self) -> None:
        """当たった → まだ分からない → 当たった では、まだ分からないを飛ばして数えるので、3 回目で当たったに確定する。"""
        expectation = _expectation()

        events = _record_all(
            expectation,
            Check(turn=11, verdict=HIT),
            Check(turn=12, verdict=UNDETERMINED),
            Check(turn=13, verdict=HIT),
        )

        assert events[:2] == [None, None]
        assert isinstance(events[2], ExpectationSettled)
        assert events[2].outcome is Outcome.HIT
        assert events[2].turn == 13

    def test_hit_undetermined_miss_reports_provisional_miss(self) -> None:
        """当たった → まだ分からない → 外れた では、当否つきの直前の照合と違うので確定せず、暫定の出来事を返す。"""
        expectation = _expectation()

        events = _record_all(
            expectation,
            Check(turn=11, verdict=HIT),
            Check(turn=12, verdict=UNDETERMINED),
            Check(turn=13, verdict=MISS),
        )

        assert isinstance(events[2], ProvisionallyMissed)
        assert _outcome_when_overdue(expectation) is Outcome.MISS

    def test_miss_after_undetermined_settles_as_miss(self) -> None:
        """外れた → まだ分からない → 外れた では、まだ分からないを飛ばして数えるので、3 回目で外れたに確定する。"""
        expectation = _expectation()

        events = _record_all(
            expectation,
            Check(turn=11, verdict=MISS),
            Check(turn=12, verdict=UNDETERMINED),
            Check(turn=13, verdict=MISS),
        )

        assert isinstance(events[0], ProvisionallyMissed)
        assert events[1] is None
        assert isinstance(events[2], ExpectationSettled)
        assert events[2].outcome is Outcome.MISS

    def test_undetermined_keeps_previous_provisional_outcome(self) -> None:
        """まだ分からないは前の判定を打ち消さないので、外れた → まだ分からない のあと期限を過ぎると外れたで確定する。"""
        expectation = _expectation()
        _record_all(
            expectation,
            Check(turn=11, verdict=MISS),
            Check(turn=12, verdict=UNDETERMINED),
        )

        assert _outcome_when_overdue(expectation) is Outcome.MISS

    def test_hit_then_miss_reports_provisional_miss(self) -> None:
        """当たった → 外れた と変わったら、外れたターンで暫定の出来事を返す。"""
        expectation = _expectation()

        events = _record_all(
            expectation, Check(turn=11, verdict=HIT), Check(turn=12, verdict=MISS)
        )

        assert isinstance(events[1], ProvisionallyMissed)
        assert events[1].turn == 12

    def test_alternating_outcomes_report_provisional_miss_on_each_miss(self) -> None:
        """外れた → 当たった → 外れた と交互に続くあいだは確定せず、外れるたびに暫定の出来事を返す。"""
        expectation = _expectation()

        events = _record_all(
            expectation,
            Check(turn=11, verdict=MISS),
            Check(turn=12, verdict=HIT),
            Check(turn=13, verdict=MISS),
        )

        assert isinstance(events[0], ProvisionallyMissed)
        assert events[1] is None
        assert isinstance(events[2], ProvisionallyMissed)
        assert events[2].turn == 13

    def test_not_an_expectation_check_voids_without_settlement(self) -> None:
        """照合で予期になっていないと判定されたら、確定させずに外した出来事を返し、以後は判定を受け取らない。"""
        expectation = _expectation()

        event = expectation.record(
            Check(turn=11, verdict=CheckVerdict.NOT_AN_EXPECTATION)
        )

        assert event == ExpectationVoided(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=11,
        )
        _assert_closed(expectation)

    def test_not_an_expectation_after_hit_voids_instead_of_settling(self) -> None:
        """当たった → 予期になっていない では、当たったで確定させずに外した出来事を返す。"""
        expectation = _expectation()
        expectation.record(Check(turn=11, verdict=HIT))

        event = expectation.record(
            Check(turn=12, verdict=CheckVerdict.NOT_AN_EXPECTATION)
        )

        assert isinstance(event, ExpectationVoided)
        _assert_closed(expectation)

    def test_record_rejects_non_check(self) -> None:
        """Check 以外を渡すと ExpectationValidationException を投げる。"""
        expectation = _expectation()

        with pytest.raises(ExpectationValidationException):
            expectation.record("hit")  # type: ignore[arg-type]


class TestCheckTurnRules:
    """照合のターンが、作ったターン・前回の照合・期限と矛盾したら受け取らず、記録にも残さない挙動を保証する。"""

    def test_check_before_formed_turn_raises_and_is_not_recorded(self) -> None:
        """作ったターンより前の照合を渡すと ExpectationCheckRuleException を投げ、その照合は直前の照合に数えない。"""
        expectation = _expectation(formed_at_turn=10)

        with pytest.raises(ExpectationCheckRuleException, match="formed_at_turn"):
            expectation.record(Check(turn=9, verdict=HIT))

        assert expectation.record(Check(turn=11, verdict=HIT)) is None

    def test_check_at_formed_turn_is_accepted(self) -> None:
        """作ったターンちょうどの照合は受け取る。信念から書き出した予期は、作ったターンに最初の照合を持つ。"""
        expectation = _expectation(
            origin=ExpectationOrigin.FROM_BELIEF, formed_at_turn=10
        )

        event = expectation.record(Check(turn=10, verdict=MISS))

        assert isinstance(event, ProvisionallyMissed)

    def test_check_before_previous_check_turn_raises(self) -> None:
        """前回の照合より前のターンの照合を渡すと ExpectationCheckRuleException を投げる。"""
        expectation = _expectation()
        expectation.record(Check(turn=12, verdict=HIT))

        with pytest.raises(ExpectationCheckRuleException, match="previous check"):
            expectation.record(Check(turn=11, verdict=HIT))

    def test_second_check_in_same_turn_raises_and_is_not_recorded(self) -> None:
        """同じターンに 2 回目の照合を渡すと ExpectationCheckRuleException を投げ、直前の照合は 1 回目のまま残る。"""
        expectation = _expectation()
        expectation.record(Check(turn=11, verdict=MISS))

        with pytest.raises(ExpectationCheckRuleException, match="previous check"):
            expectation.record(Check(turn=11, verdict=HIT))

        event = expectation.record(Check(turn=12, verdict=MISS))
        assert isinstance(event, ExpectationSettled)
        assert event.outcome is Outcome.MISS

    def test_check_after_expiry_turn_raises(self) -> None:
        """期限のターンを過ぎた照合を渡すと ExpectationCheckRuleException を投げる。期限の扱いが先に要る。"""
        expectation = _expectation()

        with pytest.raises(ExpectationCheckRuleException, match="expires_at_turn"):
            expectation.record(Check(turn=EXPIRES_AT + 1, verdict=HIT))

        assert _outcome_when_overdue(expectation) is None

    def test_check_at_expiry_turn_is_accepted(self) -> None:
        """期限のターンちょうどの照合は受け取る。"""
        expectation = _expectation()

        event = expectation.record(Check(turn=EXPIRES_AT, verdict=MISS))

        assert isinstance(event, ProvisionallyMissed)


class TestJudgeShape:
    """形の判定を受け取り、清算できない形の予期を照合に回さず外す挙動を保証する。"""

    @pytest.mark.parametrize(
        "shape",
        [
            ShapeVerdict.TRUE_EITHER_WAY,
            ShapeVerdict.OWN_ACTION,
            ShapeVerdict.NOT_AN_EXPECTATION,
        ],
    )
    def test_unsettleable_shape_dismisses_and_emits_dismissed(
        self, shape: ShapeVerdict
    ) -> None:
        """形の判定が どう転んでも当たる / 本人の行動 / 予期ではない なら、清算に回さず外した出来事を返し、以後は照合を受け取らない。"""
        expectation = _expectation()

        event = expectation.judge_shape(shape, turn=10)

        assert event == ExpectationDismissed(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=10,
            shape=shape,
        )
        _assert_closed(expectation)

    def test_settleable_shape_keeps_expectation_open(self) -> None:
        """形の判定が清算できる予期なら出来事を返さず、清算待ちのまま照合を受け取る。"""
        expectation = _expectation()

        event = expectation.judge_shape(ShapeVerdict.SETTLEABLE, turn=10)

        assert event is None
        assert isinstance(
            expectation.record(Check(turn=11, verdict=MISS)), ProvisionallyMissed
        )

    def test_second_shape_judgment_raises_and_keeps_expectation_open(self) -> None:
        """形の判定を 2 回渡すと ExpectationCheckRuleException を投げ、2 回目の「本人の行動」では外されない。"""
        expectation = _expectation()
        expectation.judge_shape(ShapeVerdict.SETTLEABLE, turn=10)

        with pytest.raises(ExpectationCheckRuleException, match="shape"):
            expectation.judge_shape(ShapeVerdict.OWN_ACTION, turn=10)

        assert expectation.record(Check(turn=11, verdict=HIT)) is None

    def test_shape_judgment_after_first_check_raises_and_keeps_expectation_open(
        self,
    ) -> None:
        """照合を 1 件でも受け取ったあとに形の判定を渡すと ExpectationCheckRuleException を投げ、外されない。"""
        expectation = _expectation()
        expectation.record(Check(turn=11, verdict=HIT))

        with pytest.raises(
            ExpectationCheckRuleException, match="before the first check"
        ):
            expectation.judge_shape(ShapeVerdict.OWN_ACTION, turn=11)

        assert isinstance(
            expectation.record(Check(turn=12, verdict=HIT)), ExpectationSettled
        )

    def test_shape_judgment_after_expiry_turn_raises(self) -> None:
        """期限のターンを過ぎた形の判定を渡すと ExpectationCheckRuleException を投げる。"""
        expectation = _expectation()

        with pytest.raises(ExpectationCheckRuleException, match="expires_at_turn"):
            expectation.judge_shape(ShapeVerdict.SETTLEABLE, turn=EXPIRES_AT + 1)

    def test_shape_judgment_before_formed_turn_raises(self) -> None:
        """作ったターンより前の形の判定を渡すと ExpectationCheckRuleException を投げる。"""
        expectation = _expectation(formed_at_turn=10)

        with pytest.raises(ExpectationCheckRuleException, match="formed_at_turn"):
            expectation.judge_shape(ShapeVerdict.SETTLEABLE, turn=9)

    @pytest.mark.parametrize(
        "shape, turn",
        [
            pytest.param("own_action", 10, id="shape_not_enum"),
            pytest.param(ShapeVerdict.OWN_ACTION, True, id="bool_turn"),
        ],
    )
    def test_invalid_shape_or_turn_raises(self, shape: Any, turn: Any) -> None:
        """ShapeVerdict 以外の判定や bool のターンを渡すと ExpectationValidationException を投げ、外されない。"""
        expectation = _expectation()

        with pytest.raises(ExpectationValidationException):
            expectation.judge_shape(shape, turn=turn)

        assert expectation.record(Check(turn=11, verdict=HIT)) is None


class TestExpireIfOverdue:
    """期限のターンを過ぎたとき、最後の照合に応じて確定か期限切れに移る規則を保証する。"""

    def test_overdue_with_last_miss_settles_as_miss(self) -> None:
        """期限のターンを過ぎたとき、最後の判定が外れたなら外れたで確定し、以後は判定を受け取らない。"""
        expectation = _expectation(beliefs_in_mind=("belief-1",))
        _record_all(
            expectation,
            Check(turn=19, verdict=HIT),
            Check(turn=EXPIRES_AT, verdict=MISS),
        )

        event = expectation.expire_if_overdue(now_turn=EXPIRES_AT + 1)

        assert event == ExpectationSettled(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=EXPIRES_AT + 1,
            outcome=Outcome.MISS,
            likelihood=Likelihood.PROBABLY,
            beliefs_in_mind=("belief-1",),
            episodes_in_mind=(),
        )
        _assert_closed(expectation)

    def test_overdue_with_last_hit_settles_as_hit(self) -> None:
        """期限のターンを過ぎたとき、最後の判定が当たったなら当たったで確定する。"""
        expectation = _expectation(likelihood=Likelihood.MAYBE)
        expectation.record(Check(turn=EXPIRES_AT, verdict=HIT))

        event = expectation.expire_if_overdue(now_turn=EXPIRES_AT + 1)

        assert isinstance(event, ExpectationSettled)
        assert event.outcome is Outcome.HIT
        assert event.likelihood is Likelihood.MAYBE

    def test_overdue_after_hit_then_undetermined_settles_as_hit(self) -> None:
        """当たった → まだ分からない のあとで期限のターンを過ぎたら、期限切れにせず当たったで確定する。"""
        expectation = _expectation()
        _record_all(
            expectation,
            Check(turn=19, verdict=HIT),
            Check(turn=EXPIRES_AT, verdict=UNDETERMINED),
        )

        event = expectation.expire_if_overdue(now_turn=EXPIRES_AT + 1)

        assert isinstance(event, ExpectationSettled)
        assert event.outcome is Outcome.HIT

    def test_overdue_with_only_undetermined_expires(self) -> None:
        """当否つきの照合が一度も無いまま期限のターンを過ぎたら期限切れになり、以後は判定を受け取らない。"""
        expectation = _expectation()
        _record_all(
            expectation,
            Check(turn=19, verdict=UNDETERMINED),
            Check(turn=EXPIRES_AT, verdict=UNDETERMINED),
        )

        event = expectation.expire_if_overdue(now_turn=EXPIRES_AT + 1)

        assert event == ExpectationExpired(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=EXPIRES_AT + 1,
        )
        _assert_closed(expectation)

    def test_not_overdue_at_expiry_turn_keeps_open(self) -> None:
        """期限のターンちょうどでは過ぎていないので出来事を返さず、清算待ちのまま照合を受け取る。"""
        expectation = _expectation()
        expectation.record(Check(turn=19, verdict=MISS))

        event = expectation.expire_if_overdue(now_turn=EXPIRES_AT)

        assert event is None
        assert isinstance(
            expectation.record(Check(turn=EXPIRES_AT, verdict=MISS)),
            ExpectationSettled,
        )

    def test_invalid_now_turn_raises(self) -> None:
        """負のターンで期限を確かめると ExpectationValidationException を投げる。"""
        expectation = _expectation()

        with pytest.raises(ExpectationValidationException):
            expectation.expire_if_overdue(now_turn=-1)


def _settled() -> Expectation:
    expectation = _expectation()
    _record_all(expectation, Check(turn=11, verdict=HIT), Check(turn=12, verdict=HIT))
    return expectation


def _dismissed() -> Expectation:
    expectation = _expectation()
    expectation.judge_shape(ShapeVerdict.OWN_ACTION, turn=10)
    return expectation


def _voided() -> Expectation:
    expectation = _expectation()
    expectation.record(Check(turn=11, verdict=CheckVerdict.NOT_AN_EXPECTATION))
    return expectation


def _expired() -> Expectation:
    expectation = _expectation()
    expectation.expire_if_overdue(now_turn=EXPIRES_AT + 1)
    return expectation


def _record(expectation: Expectation) -> object:
    return expectation.record(Check(turn=15, verdict=MISS))


def _judge_shape(expectation: Expectation) -> object:
    return expectation.judge_shape(ShapeVerdict.TRUE_EITHER_WAY, turn=15)


def _expire(expectation: Expectation) -> object:
    return expectation.expire_if_overdue(now_turn=99)


_OPERATIONS = [_record, _judge_shape, _expire]


class TestClosedExpectation:
    """清算待ちを抜けた予期は、それ以上判定も期限の確認も受け取らず、拒んだあとも閉じたままでいる挙動を保証する。"""

    @pytest.mark.parametrize(
        "close", [_settled, _dismissed, _voided, _expired], ids=lambda f: f.__name__
    )
    @pytest.mark.parametrize("operate", _OPERATIONS, ids=lambda f: f.__name__)
    def test_any_operation_after_closure_raises_and_stays_closed(
        self,
        close: Callable[[], Expectation],
        operate: Callable[[Expectation], object],
    ) -> None:
        """確定・外した・予期になっていなかった・期限切れのどれのあとでも、照合・形の判定・期限の確認を渡すと ExpectationAlreadyClosedException を投げ、ほかの操作も拒み続ける。"""
        expectation = close()

        with pytest.raises(ExpectationAlreadyClosedException):
            operate(expectation)

        for other in _OPERATIONS:
            with pytest.raises(ExpectationAlreadyClosedException):
                other(expectation)
