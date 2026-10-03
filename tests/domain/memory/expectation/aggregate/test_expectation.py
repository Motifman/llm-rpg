"""予期 (Expectation) が照合・形の判定・期限を受けて状態を移す規則を保証する。"""

from __future__ import annotations

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


def _expectation(**overrides: Any) -> Expectation:
    fields: dict[str, Any] = {
        "expectation_id": ExpectationId("exp-1"),
        "holder": BeingId("being-rio"),
        "content": "箱を開けても空だろう",
        "origin": ExpectationOrigin.WITH_ACTION,
        "likelihood": Likelihood.PROBABLY,
        "formed_at_turn": 10,
        "expires_at_turn": 20,
    }
    fields.update(overrides)
    return Expectation(**fields)


class TestFormation:
    """予期を作るときに、持ったときの文脈を保持し、時刻の矛盾を拒む挙動を保証する。"""

    def test_new_expectation_is_open_without_checks(self) -> None:
        """作ったばかりの予期は清算待ちで、照合の記録も暫定の判定も持たない。"""
        expectation = _expectation()

        assert expectation.status is ExpectationStatus.OPEN
        assert expectation.checks == ()
        assert expectation.provisional_outcome is None
        assert expectation.settled_outcome is None

    def test_keeps_beliefs_and_episodes_in_mind_at_formation(self) -> None:
        """持ったときに頭にあった信念とエピソードの ID を、渡した順に保持する。"""
        expectation = _expectation(
            beliefs_in_mind=("belief-1", "belief-2"),
            episodes_in_mind=("episode-9",),
        )

        assert expectation.beliefs_in_mind == ("belief-1", "belief-2")
        assert expectation.episodes_in_mind == ("episode-9",)

    def test_strips_surrounding_whitespace_of_texts(self) -> None:
        """予期の文と ID の前後の空白は落として保持する。"""
        expectation = _expectation(content="  箱は空だろう ", beliefs_in_mind=(" belief-1 ",))

        assert expectation.content == "箱は空だろう"
        assert expectation.beliefs_in_mind == ("belief-1",)

    def test_keeps_due_and_formed_with_as_text(self) -> None:
        """期日と、持ったときの行動は、計算せずに文のまま保持する。"""
        expectation = _expectation(
            origin=ExpectationOrigin.PROMISE_OR_OUTLOOK,
            formed_with="ノアに話しかける",
            due="二日後の朝",
        )

        assert expectation.formed_with == "ノアに話しかける"
        assert expectation.due == "二日後の朝"

    def test_expiry_turn_before_formed_turn_raises(self) -> None:
        """期限のターンが作ったターンより前なら ExpectationValidationException を投げる。"""
        with pytest.raises(ExpectationValidationException, match="expires_at_turn"):
            _expectation(formed_at_turn=10, expires_at_turn=9)

    def test_expiry_turn_equal_to_formed_turn_is_allowed(self) -> None:
        """期限のターンが作ったターンと同じなら作れる。"""
        expectation = _expectation(formed_at_turn=10, expires_at_turn=10)

        assert expectation.expires_at_turn == 10

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
        """まだ分からないが続くあいだは、清算待ちのまま出来事を返さない。"""
        expectation = _expectation()

        events = [
            expectation.record(Check(turn=turn, verdict=UNDETERMINED))
            for turn in (11, 12, 13)
        ]

        assert events == [None, None, None]
        assert expectation.status is ExpectationStatus.OPEN
        assert expectation.provisional_outcome is None

    def test_two_consecutive_hits_settle_and_emit_settled_once(self) -> None:
        """当たったが 2 回続くと当たったで確定し、確定の出来事は 2 回目にだけ返す。"""
        expectation = _expectation()

        first = expectation.record(Check(turn=11, verdict=HIT))
        second = expectation.record(Check(turn=12, verdict=HIT))

        assert first is None
        assert second == ExpectationSettled(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=12,
            outcome=Outcome.HIT,
            likelihood=Likelihood.PROBABLY,
        )
        assert expectation.status is ExpectationStatus.SETTLED
        assert expectation.settled_outcome is Outcome.HIT

    def test_miss_then_hit_stays_provisional_and_reports_first_miss(self) -> None:
        """外れた → 当たった と変わったときは確定せず、1 回目の外れで暫定の出来事を返す。"""
        expectation = _expectation(likelihood=Likelihood.ALMOST_CERTAIN)

        first = expectation.record(Check(turn=11, verdict=MISS))
        second = expectation.record(Check(turn=12, verdict=HIT))

        assert first == ProvisionallyMissed(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=11,
            likelihood=Likelihood.ALMOST_CERTAIN,
        )
        assert second is None
        assert expectation.status is ExpectationStatus.OPEN
        assert expectation.provisional_outcome is Outcome.HIT

    def test_two_consecutive_misses_settle_as_miss_without_second_provisional_event(
        self,
    ) -> None:
        """外れたが 2 回続くと外れたで確定し、2 回目は暫定ではなく確定の出来事だけを返す。"""
        expectation = _expectation()

        expectation.record(Check(turn=11, verdict=MISS))
        second = expectation.record(Check(turn=12, verdict=MISS))

        assert isinstance(second, ExpectationSettled)
        assert second.outcome is Outcome.MISS
        assert expectation.settled_outcome is Outcome.MISS

    def test_undetermined_between_same_outcomes_prevents_settlement(self) -> None:
        """当たった → まだ分からない → 当たった では、直前の判定と続いていないので確定しない。"""
        expectation = _expectation()

        expectation.record(Check(turn=11, verdict=HIT))
        expectation.record(Check(turn=12, verdict=UNDETERMINED))
        third = expectation.record(Check(turn=13, verdict=HIT))

        assert third is None
        assert expectation.status is ExpectationStatus.OPEN

    def test_miss_after_undetermined_reports_provisional_miss_again(self) -> None:
        """外れた → まだ分からない → 外れた では確定せず、3 回目の外れでも暫定の出来事を返す。"""
        expectation = _expectation()
        expectation.record(Check(turn=11, verdict=MISS))
        expectation.record(Check(turn=12, verdict=UNDETERMINED))

        third = expectation.record(Check(turn=13, verdict=MISS))

        assert isinstance(third, ProvisionallyMissed)
        assert third.turn == 13
        assert expectation.status is ExpectationStatus.OPEN

    def test_undetermined_clears_provisional_outcome(self) -> None:
        """暫定の判定は最後の照合で決まり、まだ分からないが来ると暫定の判定は無くなる。"""
        expectation = _expectation()

        expectation.record(Check(turn=11, verdict=MISS))
        expectation.record(Check(turn=12, verdict=UNDETERMINED))

        assert expectation.provisional_outcome is None

    def test_hit_then_miss_reports_provisional_miss(self) -> None:
        """当たった → 外れた と変わったら、外れたターンで暫定の出来事を返す。"""
        expectation = _expectation()

        expectation.record(Check(turn=11, verdict=HIT))
        second = expectation.record(Check(turn=12, verdict=MISS))

        assert isinstance(second, ProvisionallyMissed)
        assert second.turn == 12

    def test_not_an_expectation_check_voids_without_settlement(self) -> None:
        """照合で予期になっていないと判定されたら、確定させずに外し、外した出来事を返す。"""
        expectation = _expectation()

        event = expectation.record(
            Check(turn=11, verdict=CheckVerdict.NOT_AN_EXPECTATION)
        )

        assert event == ExpectationVoided(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=11,
        )
        assert expectation.status is ExpectationStatus.VOIDED
        assert expectation.settled_outcome is None

    def test_not_an_expectation_after_hit_voids_instead_of_settling(self) -> None:
        """当たった → 予期になっていない では確定せずに外し、どちらの照合も記録に残る。"""
        expectation = _expectation()
        expectation.record(Check(turn=11, verdict=HIT))

        event = expectation.record(
            Check(turn=12, verdict=CheckVerdict.NOT_AN_EXPECTATION)
        )

        assert isinstance(event, ExpectationVoided)
        assert expectation.settled_outcome is None
        assert expectation.provisional_outcome is None
        assert [c.verdict for c in expectation.checks] == [
            HIT,
            CheckVerdict.NOT_AN_EXPECTATION,
        ]

    def test_checks_are_kept_in_order(self) -> None:
        """受け取った照合は、受け取った順に記録として残る。"""
        expectation = _expectation()
        first = Check(turn=11, verdict=UNDETERMINED)
        second = Check(turn=12, verdict=MISS)

        expectation.record(first)
        expectation.record(second)

        assert expectation.checks == (first, second)

    def test_record_rejects_non_check(self) -> None:
        """Check 以外を渡すと ExpectationValidationException を投げる。"""
        expectation = _expectation()

        with pytest.raises(ExpectationValidationException):
            expectation.record("hit")  # type: ignore[arg-type]


class TestCheckTurnRules:
    """照合のターンが、作ったターン・前回の照合・期限と矛盾したら受け取らない挙動を保証する。"""

    def test_check_before_formed_turn_raises(self) -> None:
        """作ったターンより前の照合を渡すと ExpectationCheckRuleException を投げ、記録は増えない。"""
        expectation = _expectation(formed_at_turn=10)

        with pytest.raises(ExpectationCheckRuleException, match="formed_at_turn"):
            expectation.record(Check(turn=9, verdict=HIT))
        assert expectation.checks == ()

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
        assert len(expectation.checks) == 1

    def test_second_check_in_same_turn_raises(self) -> None:
        """同じターンに 2 回目の照合を渡すと ExpectationCheckRuleException を投げ、1 回目だけが残る。"""
        expectation = _expectation()
        expectation.record(Check(turn=11, verdict=HIT))

        with pytest.raises(ExpectationCheckRuleException, match="previous check"):
            expectation.record(Check(turn=11, verdict=HIT))
        assert expectation.checks == (Check(turn=11, verdict=HIT),)
        assert expectation.status is ExpectationStatus.OPEN

    def test_check_after_expiry_turn_raises(self) -> None:
        """期限のターンを過ぎた照合を渡すと ExpectationCheckRuleException を投げる。期限の扱いが先に要る。"""
        expectation = _expectation(expires_at_turn=20)

        with pytest.raises(ExpectationCheckRuleException, match="expires_at_turn"):
            expectation.record(Check(turn=21, verdict=HIT))
        assert expectation.checks == ()

    def test_check_at_expiry_turn_is_accepted(self) -> None:
        """期限のターンちょうどの照合は受け取る。"""
        expectation = _expectation(expires_at_turn=20)

        expectation.record(Check(turn=20, verdict=MISS))

        assert expectation.provisional_outcome is Outcome.MISS


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
        """形の判定が どう転んでも当たる / 本人の行動 / 予期ではない なら、清算に回さず外した出来事を返す。"""
        expectation = _expectation()

        event = expectation.judge_shape(shape, turn=10)

        assert event == ExpectationDismissed(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=10,
            shape=shape,
        )
        assert expectation.status is ExpectationStatus.DISMISSED
        assert expectation.settled_outcome is None

    def test_settleable_shape_keeps_expectation_open(self) -> None:
        """形の判定が清算できる予期なら、清算待ちのまま出来事を返さない。"""
        expectation = _expectation()

        event = expectation.judge_shape(ShapeVerdict.SETTLEABLE, turn=10)

        assert event is None
        assert expectation.status is ExpectationStatus.OPEN
        assert expectation.shape is ShapeVerdict.SETTLEABLE

    def test_second_shape_judgment_raises(self) -> None:
        """形の判定を 2 回渡すと ExpectationCheckRuleException を投げ、最初の判定が残る。"""
        expectation = _expectation()
        expectation.judge_shape(ShapeVerdict.SETTLEABLE, turn=10)

        with pytest.raises(ExpectationCheckRuleException, match="shape"):
            expectation.judge_shape(ShapeVerdict.OWN_ACTION, turn=10)
        assert expectation.shape is ShapeVerdict.SETTLEABLE
        assert expectation.status is ExpectationStatus.OPEN

    def test_shape_judgment_after_first_check_raises(self) -> None:
        """照合を 1 件でも受け取ったあとに形の判定を渡すと ExpectationCheckRuleException を投げ、外されない。"""
        expectation = _expectation()
        expectation.record(Check(turn=11, verdict=HIT))

        with pytest.raises(ExpectationCheckRuleException, match="before the first check"):
            expectation.judge_shape(ShapeVerdict.OWN_ACTION, turn=11)
        assert expectation.status is ExpectationStatus.OPEN
        assert expectation.shape is None

    def test_shape_judgment_after_expiry_turn_raises(self) -> None:
        """期限のターンを過ぎた形の判定を渡すと ExpectationCheckRuleException を投げる。"""
        expectation = _expectation(expires_at_turn=20)

        with pytest.raises(ExpectationCheckRuleException, match="expires_at_turn"):
            expectation.judge_shape(ShapeVerdict.SETTLEABLE, turn=21)

    @pytest.mark.parametrize(
        "shape, turn",
        [
            pytest.param("own_action", 10, id="shape_not_enum"),
            pytest.param(ShapeVerdict.OWN_ACTION, True, id="bool_turn"),
        ],
    )
    def test_invalid_shape_or_turn_raises(self, shape: Any, turn: Any) -> None:
        """ShapeVerdict 以外の判定や bool のターンを渡すと ExpectationValidationException を投げる。"""
        expectation = _expectation()

        with pytest.raises(ExpectationValidationException):
            expectation.judge_shape(shape, turn=turn)
        assert expectation.status is ExpectationStatus.OPEN

    def test_shape_judgment_before_formed_turn_raises(self) -> None:
        """作ったターンより前の形の判定を渡すと ExpectationCheckRuleException を投げる。"""
        expectation = _expectation(formed_at_turn=10)

        with pytest.raises(ExpectationCheckRuleException, match="formed_at_turn"):
            expectation.judge_shape(ShapeVerdict.SETTLEABLE, turn=9)


class TestExpireIfOverdue:
    """期限のターンを過ぎたとき、最後の照合に応じて確定か期限切れに移る規則を保証する。"""

    def test_overdue_with_last_miss_settles_as_miss(self) -> None:
        """期限のターンを過ぎたとき、最後の判定が外れたなら外れたで確定する。"""
        expectation = _expectation(expires_at_turn=20)
        expectation.record(Check(turn=19, verdict=HIT))
        expectation.record(Check(turn=20, verdict=MISS))

        event = expectation.expire_if_overdue(now_turn=21)

        assert event == ExpectationSettled(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=21,
            outcome=Outcome.MISS,
            likelihood=Likelihood.PROBABLY,
        )
        assert expectation.status is ExpectationStatus.SETTLED
        assert expectation.settled_outcome is Outcome.MISS

    def test_overdue_with_last_hit_settles_as_hit(self) -> None:
        """期限のターンを過ぎたとき、最後の判定が当たったなら当たったで確定する。"""
        expectation = _expectation(expires_at_turn=20, likelihood=Likelihood.MAYBE)
        expectation.record(Check(turn=20, verdict=HIT))

        event = expectation.expire_if_overdue(now_turn=21)

        assert isinstance(event, ExpectationSettled)
        assert event.outcome is Outcome.HIT
        assert event.likelihood is Likelihood.MAYBE
        assert expectation.settled_outcome is Outcome.HIT

    def test_overdue_with_last_undetermined_expires(self) -> None:
        """期限のターンを過ぎたとき、最後の判定がまだ分からないなら期限切れになる。"""
        expectation = _expectation(expires_at_turn=20)
        expectation.record(Check(turn=19, verdict=HIT))
        expectation.record(Check(turn=20, verdict=UNDETERMINED))

        event = expectation.expire_if_overdue(now_turn=21)

        assert event == ExpectationExpired(
            expectation_id=ExpectationId("exp-1"),
            holder=BeingId("being-rio"),
            turn=21,
        )
        assert expectation.status is ExpectationStatus.EXPIRED
        assert expectation.settled_outcome is None

    def test_overdue_without_checks_expires(self) -> None:
        """一度も照合されないまま期限のターンを過ぎたら期限切れになる。"""
        expectation = _expectation(expires_at_turn=20)

        event = expectation.expire_if_overdue(now_turn=25)

        assert isinstance(event, ExpectationExpired)
        assert expectation.status is ExpectationStatus.EXPIRED

    def test_not_overdue_at_expiry_turn_keeps_open(self) -> None:
        """期限のターンちょうどでは過ぎていないので、清算待ちのまま出来事を返さない。"""
        expectation = _expectation(expires_at_turn=20)
        expectation.record(Check(turn=20, verdict=MISS))

        event = expectation.expire_if_overdue(now_turn=20)

        assert event is None
        assert expectation.status is ExpectationStatus.OPEN

    def test_invalid_now_turn_raises(self) -> None:
        """負のターンで期限を確かめると ExpectationValidationException を投げる。"""
        expectation = _expectation()

        with pytest.raises(ExpectationValidationException):
            expectation.expire_if_overdue(now_turn=-1)


def _settled() -> Expectation:
    expectation = _expectation(expires_at_turn=20)
    expectation.record(Check(turn=11, verdict=HIT))
    expectation.record(Check(turn=12, verdict=HIT))
    return expectation


def _dismissed() -> Expectation:
    expectation = _expectation(expires_at_turn=20)
    expectation.judge_shape(ShapeVerdict.OWN_ACTION, turn=10)
    return expectation


def _voided() -> Expectation:
    expectation = _expectation(expires_at_turn=20)
    expectation.record(Check(turn=11, verdict=CheckVerdict.NOT_AN_EXPECTATION))
    return expectation


def _expired() -> Expectation:
    expectation = _expectation(expires_at_turn=20)
    expectation.expire_if_overdue(now_turn=21)
    return expectation


def _record(expectation: Expectation) -> object:
    return expectation.record(Check(turn=15, verdict=MISS))


def _judge_shape(expectation: Expectation) -> object:
    return expectation.judge_shape(ShapeVerdict.TRUE_EITHER_WAY, turn=15)


def _expire(expectation: Expectation) -> object:
    return expectation.expire_if_overdue(now_turn=99)


class TestClosedExpectation:
    """清算待ちを抜けた予期は、それ以上判定も期限の確認も受け取らず、状態も記録も変えない挙動を保証する。"""

    @pytest.mark.parametrize(
        "close", [_settled, _dismissed, _voided, _expired], ids=lambda f: f.__name__
    )
    @pytest.mark.parametrize(
        "operate", [_record, _judge_shape, _expire], ids=lambda f: f.__name__
    )
    def test_any_operation_after_closure_raises_and_keeps_state(
        self, close: Any, operate: Any
    ) -> None:
        """確定・外した・予期になっていなかった・期限切れのどれのあとでも、照合・形の判定・期限の確認を渡すと ExpectationAlreadyClosedException を投げ、状態・確定の当否・記録・形は変わらない。"""
        expectation = close()
        before = (
            expectation.status,
            expectation.settled_outcome,
            expectation.checks,
            expectation.shape,
        )

        with pytest.raises(ExpectationAlreadyClosedException):
            operate(expectation)

        after = (
            expectation.status,
            expectation.settled_outcome,
            expectation.checks,
            expectation.shape,
        )
        assert after == before

    def test_settled_expectation_has_no_provisional_outcome(self) -> None:
        """確定した予期は暫定の判定を持たず、確定の当否だけを持つ。"""
        expectation = _settled()

        assert expectation.provisional_outcome is None
        assert expectation.settled_outcome is Outcome.HIT
