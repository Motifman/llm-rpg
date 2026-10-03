"""予期の根拠 (頭にあったもののうち、予期の材料になった信念とエピソード) を、形の判定と一緒に受け取り、確定の出来事で運ぶ挙動を保証する。"""

from __future__ import annotations

from dataclasses import replace
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
    ExpectationCheckRuleException,
    ExpectationValidationException,
)
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
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
from ai_rpg_world.domain.memory.expectation.value_object.expectation_status import (
    ExpectationStatus,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)

SETTLEABLE = ShapeVerdict.SETTLEABLE
HIT = CheckVerdict.HIT


def _expectation(**overrides: Any) -> Expectation:
    fields: dict[str, Any] = {
        "expectation_id": ExpectationId("exp-1"),
        "holder": BeingId("being-rio"),
        "content": "トムが麦束を焼いてくれる",
        "origin": ExpectationOrigin.WITH_ACTION,
        "likelihood": Likelihood.PROBABLY,
        "formed_at_turn": 10,
        "expires_at_turn": 20,
        "beliefs_in_mind": ("belief-tidal-flat", "belief-tom-kind"),
        "episodes_in_mind": ("ep-crab", "ep-bread"),
    }
    fields.update(overrides)
    return Expectation(**fields)


def _settle_hit(expectation: Expectation) -> ExpectationSettled:
    expectation.record(Check(turn=11, verdict=HIT))
    event = expectation.record(Check(turn=12, verdict=HIT))
    assert isinstance(event, ExpectationSettled)
    return event


class TestExpectationGroundsValue:
    """根拠の値が、空でない ID の重複の無い組だけを受け付ける挙動を保証する。"""

    def test_default_grounds_are_empty(self) -> None:
        """引数を省いた根拠は、信念もエピソードも 0 件で、空と判定される。"""
        grounds = ExpectationGrounds()

        assert grounds.beliefs == ()
        assert grounds.episodes == ()
        assert grounds.is_empty

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({"beliefs": ("b-1", "b-1")}, id="duplicate_belief"),
            pytest.param({"episodes": ("",)}, id="blank_episode"),
            pytest.param({"beliefs": ["b-1"]}, id="beliefs_not_tuple"),
            pytest.param({"episodes": (1,)}, id="non_str_episode"),
        ],
    )
    def test_invalid_ids_raise(self, fields: dict[str, Any]) -> None:
        """重複・空文字・tuple でない・文字列でない ID は ExpectationValidationException を投げる。"""
        with pytest.raises(ExpectationValidationException):
            ExpectationGrounds(**fields)


class TestGroundsJudgedWithShape:
    """形の判定と一緒に根拠を受け取り、確定の出来事が根拠だけを運ぶ挙動を保証する。"""

    def test_settled_event_carries_only_grounds_not_everything_in_mind(self) -> None:
        """頭に信念 2 件とエピソード 2 件があっても、根拠と判断した 1 件ずつだけを確定の出来事が運ぶ。"""
        expectation = _expectation()
        expectation.judge_shape(
            SETTLEABLE,
            turn=10,
            grounds=ExpectationGrounds(beliefs=("belief-tom-kind",), episodes=("ep-bread",)),
        )

        event = _settle_hit(expectation)

        assert event.grounds == ExpectationGrounds(
            beliefs=("belief-tom-kind",), episodes=("ep-bread",)
        )

    def test_settled_without_shape_judgment_has_empty_grounds(self) -> None:
        """形の判定を受けないまま確定した予期は、根拠を判断していないので空の根拠を運び、頭にあったものに倒れない。"""
        expectation = _expectation()

        event = _settle_hit(expectation)

        assert event.grounds.is_empty

    @pytest.mark.parametrize(
        "grounds",
        [
            pytest.param(ExpectationGrounds(beliefs=("belief-other",)), id="belief_not_in_mind"),
            pytest.param(ExpectationGrounds(episodes=("ep-other",)), id="episode_not_in_mind"),
        ],
    )
    def test_grounds_not_in_mind_raise_and_shape_stays_unjudged(
        self, grounds: ExpectationGrounds
    ) -> None:
        """頭に無かった信念やエピソードを根拠に渡すと ExpectationValidationException を投げ、形もまだ判定されていないまま残る。"""
        expectation = _expectation()

        with pytest.raises(ExpectationValidationException, match="in mind"):
            expectation.judge_shape(SETTLEABLE, turn=10, grounds=grounds)

        assert expectation.awaits_shape

    def test_grounds_must_be_expectation_grounds(self) -> None:
        """根拠に ExpectationGrounds 以外を渡すと ExpectationValidationException を投げる。"""
        expectation = _expectation()

        with pytest.raises(ExpectationValidationException, match="grounds"):
            expectation.judge_shape(SETTLEABLE, turn=10, grounds=("belief-tom-kind",))  # type: ignore[arg-type]

    def test_second_shape_judgment_does_not_replace_grounds(self) -> None:
        """形を判定した予期にもう一度形と根拠を渡すと ExpectationCheckRuleException を投げ、最初の根拠が確定の出来事に残る。"""
        expectation = _expectation()
        first = ExpectationGrounds(beliefs=("belief-tom-kind",))
        expectation.judge_shape(SETTLEABLE, turn=10, grounds=first)

        with pytest.raises(ExpectationCheckRuleException):
            expectation.judge_shape(
                SETTLEABLE,
                turn=10,
                grounds=ExpectationGrounds(beliefs=("belief-tidal-flat",)),
            )

        assert _settle_hit(expectation).grounds == first


class TestGroundsSnapshot:
    """根拠を保存して戻し、形の判定と根拠の有無が食い違う状態を拒む挙動を保証する。"""

    def test_round_trip_keeps_grounds(self) -> None:
        """根拠を受けた予期を snapshot から戻すと、確定の出来事が同じ根拠を運ぶ。"""
        expectation = _expectation()
        grounds = ExpectationGrounds(beliefs=("belief-tom-kind",), episodes=("ep-bread",))
        expectation.judge_shape(SETTLEABLE, turn=10, grounds=grounds)

        restored = Expectation.restore(expectation.snapshot())

        assert restored.snapshot().grounds == grounds
        assert _settle_hit(restored).grounds == grounds

    def test_shape_without_grounds_is_rejected(self) -> None:
        """形の判定があるのに根拠が None の状態は、根拠を捏造せずに ExpectationValidationException で拒む。"""
        expectation = _expectation()
        expectation.judge_shape(SETTLEABLE, turn=10, grounds=ExpectationGrounds())
        snapshot = replace(expectation.snapshot(), grounds=None)

        with pytest.raises(ExpectationValidationException, match="grounds"):
            Expectation.restore(snapshot)

    def test_grounds_without_shape_is_rejected(self) -> None:
        """形の判定が無いのに根拠がある状態は ExpectationValidationException で拒む。"""
        snapshot = replace(_expectation().snapshot(), grounds=ExpectationGrounds())

        with pytest.raises(ExpectationValidationException, match="grounds"):
            Expectation.restore(snapshot)

    def test_grounds_not_in_mind_are_rejected_on_restore(self) -> None:
        """頭に無かった ID を根拠に持つ状態は ExpectationValidationException で拒む。"""
        expectation = _expectation()
        expectation.judge_shape(SETTLEABLE, turn=10, grounds=ExpectationGrounds())
        snapshot = replace(
            expectation.snapshot(), grounds=ExpectationGrounds(beliefs=("belief-other",))
        )

        with pytest.raises(ExpectationValidationException, match="in mind"):
            Expectation.restore(snapshot)

    def test_unjudged_expectation_round_trips_with_no_grounds(self) -> None:
        """形の判定を待つ予期は根拠を持たないまま戻り、形の判定を待ち続ける。"""
        restored = Expectation.restore(_expectation().snapshot())

        assert restored.snapshot().grounds is None
        assert restored.snapshot().status is ExpectationStatus.OPEN
        assert restored.awaits_shape

