"""ExpectationSettled が、外れの時系列 (what_happened) に材料として使えない値を受け付けない挙動を保証する (#1509)。"""

from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationSettled,
)
from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationValidationException,
)
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import Outcome
from ai_rpg_world.domain.memory.expectation.value_object.expectation_grounds import (
    ExpectationGrounds,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import Likelihood


def _settled(what_happened: Any) -> ExpectationSettled:
    return ExpectationSettled(
        expectation_id=ExpectationId("exp-1"),
        holder=BeingId("being-rio"),
        turn=5,
        content="流木を入手できる",
        outcome=Outcome.MISS,
        likelihood=Likelihood.PROBABLY,
        grounds=ExpectationGrounds(),
        what_happened=what_happened,
    )


class TestWhatHappenedValidation:
    """時系列の型と空の行を、確定の出来事を作る時点で拒む挙動を保証する。"""

    def test_tuple_of_lines_is_kept(self) -> None:
        """空でない文の tuple は、そのままの並びで持つ。"""
        settled = _settled(("浜に流木は無い", "ノア「波が運んでくる」"))

        assert settled.what_happened == ("浜に流木は無い", "ノア「波が運んでくる」")

    @pytest.mark.parametrize(
        "value",
        [["浜に流木は無い"], ("",), ("  ",), (1,)],
        ids=["list", "empty_line", "blank_line", "not_str"],
    )
    def test_unusable_what_happened_is_rejected(self, value: Any) -> None:
        """tuple でない値、空や空白だけの行、文字列でない行は ExpectationValidationException で拒む。材料は空の行を受け付けず、通すと配り直しのたびに受け取る側が失敗する。"""
        with pytest.raises(ExpectationValidationException):
            _settled(value)
