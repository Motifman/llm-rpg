from __future__ import annotations

from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.condition.argument_condition import ArgumentEqualsCondition
from ai_rpg_world.game_world.domain.condition.condition import AwaitsArguments, FailureReason, NoText
from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.connectives import (
    AllOfCondition,
    AnyOfCondition,
    ForEveryoneCondition,
    ForSomeoneCondition,
    NotCondition,
)
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import WorldTick
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from tests.game_world.domain.condition._builders import ALICE, text, world
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests

_BY_ALICE = ActionAttemptForTests(actor_id=ALICE)
_ROOT = ConditionPath.root()


def _true() -> TickAtLeastCondition:
    return TickAtLeastCondition(tick=WorldTick(0), failure_text=NoText())


def _false(failure_text: TextWithUnassignedPeople | NoText = NoText()) -> TickAtLeastCondition:
    return TickAtLeastCondition(tick=WorldTick(5), failure_text=failure_text)


def _code_is_1907() -> ArgumentEqualsCondition:
    return ArgumentEqualsCondition(
        argument=ArgumentName("code"), expected=TextArgumentValue("1907"), failure_text=text("扉はびくともしない")
    )


def _everyone() -> PeopleSelection:
    return PeopleSelection(where=_true())


class TestFailureReasonBeforeArguments:
    """引数の値が決まる前に、条件を「成り立つ・成り立たない・値が無いので分からない」の 3 つで確かめる決まりを保証する。"""

    def test_leaf_reading_an_argument_awaits_arguments(self) -> None:
        """引数を読む葉は、値を読まずに「分からない」を返す。"""
        reason = _code_is_1907().failure_reason_before_arguments(world().facts(), _BY_ALICE)

        assert reason == AwaitsArguments()

    def test_leaf_not_reading_arguments_is_judged_as_usual(self) -> None:
        """引数を読まない葉は、ふだんと同じく偽なら文つきの理由を返す。"""
        reason = _false(text("夜明けを待て")).failure_reason_before_arguments(world().facts(), _BY_ALICE)

        assert reason == FailureReason(failed_part=_ROOT, text=text("夜明けを待て").about({}))

    def test_all_of_fails_when_one_child_fails_even_if_another_awaits_arguments(self) -> None:
        """all_of は、分からない子が先に並んでいても、成り立たない子が 1 つあれば、その子の位置と文で成り立たない。"""
        condition = AllOfCondition(children=(_code_is_1907(), _false(text("もう開いている"))), failure_text=NoText())

        reason = condition.failure_reason_before_arguments(world().facts(), _BY_ALICE)

        assert reason == FailureReason(failed_part=_ROOT.under(1), text=text("もう開いている").about({}))

    def test_all_of_awaits_arguments_when_no_child_fails(self) -> None:
        """all_of は、成り立たない子が無く、分からない子があれば分からない。"""
        condition = AllOfCondition(children=(_true(), _code_is_1907()), failure_text=NoText())

        assert condition.failure_reason_before_arguments(world().facts(), _BY_ALICE) == AwaitsArguments()

    def test_all_of_holds_when_every_child_holds(self) -> None:
        """all_of は、子がすべて成り立てば成り立つ (None)。"""
        condition = AllOfCondition(children=(_true(), _true()), failure_text=NoText())

        assert condition.failure_reason_before_arguments(world().facts(), _BY_ALICE) is None

    def test_any_of_holds_when_one_child_holds_even_if_another_awaits_arguments(self) -> None:
        """any_of は、分からない子があっても、成り立つ子が 1 つあれば成り立つ。"""
        condition = AnyOfCondition(children=(_code_is_1907(), _true()), failure_text=NoText())

        assert condition.failure_reason_before_arguments(world().facts(), _BY_ALICE) is None

    def test_any_of_awaits_arguments_when_no_child_holds_and_one_awaits(self) -> None:
        """any_of は、成り立つ子が無く、分からない子があれば分からない。"""
        condition = AnyOfCondition(children=(_false(), _code_is_1907()), failure_text=NoText())

        assert condition.failure_reason_before_arguments(world().facts(), _BY_ALICE) == AwaitsArguments()

    def test_any_of_fails_with_own_text_when_every_child_fails(self) -> None:
        """any_of は、子がすべて成り立たなければ、自分の文で成り立たない。"""
        condition = AnyOfCondition(children=(_false(), _false()), failure_text=text("まだ早い"))

        reason = condition.failure_reason_before_arguments(world().facts(), _BY_ALICE)

        assert reason == FailureReason(failed_part=_ROOT, text=text("まだ早い").about({}))

    def test_not_keeps_awaiting_arguments(self) -> None:
        """not は、分からない子を分からないまま返す。"""
        condition = NotCondition(child=_code_is_1907(), failure_text=NoText())

        assert condition.failure_reason_before_arguments(world().facts(), _BY_ALICE) == AwaitsArguments()

    def test_not_is_judged_as_usual_when_child_is_decided(self) -> None:
        """not は、子が決まっていれば、ふだんと同じく反転して確かめる。"""
        condition = NotCondition(child=_true(), failure_text=text("もう開いている"))

        reason = condition.failure_reason_before_arguments(world().facts(), _BY_ALICE)

        assert reason == FailureReason(failed_part=_ROOT, text=text("もう開いている").about({}))

    def test_for_someone_awaits_arguments_like_any_of(self) -> None:
        """for_someone は any_of と同じく、成り立つ人が無く、分からない人があれば分からない。"""
        condition = ForSomeoneCondition(people=_everyone(), condition=_code_is_1907(), failure_text=NoText())

        assert condition.failure_reason_before_arguments(world().facts(), _BY_ALICE) == AwaitsArguments()

    def test_for_everyone_fails_when_someone_fails_like_all_of(self) -> None:
        """for_everyone は all_of と同じく、成り立たない人が 1 人いれば成り立たない。"""
        inside = AllOfCondition(children=(_code_is_1907(), _false(text("まだ早い"))), failure_text=NoText())
        condition = ForEveryoneCondition(people=_everyone(), condition=inside, failure_text=NoText())

        reason = condition.failure_reason_before_arguments(world().facts(), _BY_ALICE)

        assert isinstance(reason, FailureReason)
