"""予期の値オブジェクトが、不正な値を拒み、判定から当否を取り出す挙動を保証する。"""

from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
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
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)


class TestExpectationId:
    """ExpectationId が空の ID を拒み、前後の空白を落とす挙動を保証する。"""

    def test_strips_surrounding_whitespace(self) -> None:
        """前後に空白のある ID は、空白を落として保持する。"""
        assert ExpectationId("  exp-1 ").value == "exp-1"

    @pytest.mark.parametrize("value", ["", "   ", 1])
    def test_empty_or_non_str_raises(self, value: Any) -> None:
        """空文字・空白だけ・文字列以外を渡すと ExpectationValidationException を投げる。"""
        with pytest.raises(ExpectationValidationException):
            ExpectationId(value)


class TestCheck:
    """Check が負のターンや判定以外の値を拒む挙動を保証する。"""

    @pytest.mark.parametrize(
        "turn, verdict",
        [(-1, CheckVerdict.HIT), (True, CheckVerdict.HIT), (1, "hit")],
    )
    def test_invalid_turn_or_verdict_raises(self, turn: Any, verdict: Any) -> None:
        """負や bool のターン、CheckVerdict 以外の判定を渡すと ExpectationValidationException を投げる。"""
        with pytest.raises(ExpectationValidationException):
            Check(turn=turn, verdict=verdict)


class TestVerdicts:
    """照合の判定と形の判定が、それぞれ清算に使える情報だけを返す挙動を保証する。"""

    @pytest.mark.parametrize(
        "verdict, expected",
        [
            (CheckVerdict.HIT, Outcome.HIT),
            (CheckVerdict.MISS, Outcome.MISS),
            (CheckVerdict.UNDETERMINED, None),
            (CheckVerdict.NOT_AN_EXPECTATION, None),
        ],
    )
    def test_check_verdict_outcome_is_only_for_hit_and_miss(
        self, verdict: CheckVerdict, expected: Outcome | None
    ) -> None:
        """当たった / 外れた だけが当否を持ち、まだ分からない / 予期になっていない は None を返す。"""
        assert verdict.outcome is expected

    def test_only_settleable_shape_is_settleable(self) -> None:
        """形の判定のうち、清算に回せるのは「清算できる予期」だけである。"""
        assert [s for s in ShapeVerdict if s.is_settleable] == [ShapeVerdict.SETTLEABLE]
