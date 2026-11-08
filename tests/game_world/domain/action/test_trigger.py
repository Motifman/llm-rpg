from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson
from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.action.trigger import (
    EachPersonOf,
    GroupDecisionResult,
    HappeningFired,
    JointActionCompleted,
    ReactionFired,
    Trigger,
    WorldTimePassing,
)
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.exception.trigger_exception import (
    ArgumentNotInTriggerException,
    ItemNotInTriggerException,
    SubjectNotInTriggerException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import StruckByPerson, WorldHappening
from ai_rpg_world.game_world.domain.value_object import DisplayName, GroupDecisionId, PersonId, WorldTick
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.declarations_for_tests import (
    HappeningForTests,
    JointActionForTests,
    ReactionForTests,
)

_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_CAROL = PersonId("carol")
_LANTERN = ItemInstanceId("lantern-1")
_MESSAGE = ArgumentName("message")
_EXILE_VOTE = GroupDecisionDeclaration(
    decision_id=GroupDecisionId("exile_vote"),
    name=DisplayName("追放の投票"),
    abstain_allowed=True,
    reveals_ballots=False,
)

_TRIGGERS_WITHOUT_PEOPLE: tuple[Trigger, ...] = (
    HappeningFired(HappeningForTests(HappeningId("bell_rings"))),
    ReactionFired(ReactionForTests(ReactionId("lights_on"))),
    JointActionCompleted(JointActionForTests(JointActionId("two_valves"))),
    WorldTimePassing(WorldTick(3)),
)
_TRIGGERS_NOT_ACTIONS: tuple[Trigger, ...] = (
    *_TRIGGERS_WITHOUT_PEOPLE,
    GroupDecisionResult(_EXILE_VOTE, chosen=_BOB),
)


class TestTriggersWithoutPeople:
    """出来事・反応・二人で合わせる操作・時間の経過のきっかけが、主語も品物も答えないことを保証する。"""

    @pytest.mark.parametrize("trigger", _TRIGGERS_WITHOUT_PEOPLE)
    @pytest.mark.parametrize("kind", list(SubjectKind))
    def test_asking_any_subject_raises_domain_exception(self, trigger: Trigger, kind: SubjectKind) -> None:
        """どの種類の主語を尋ねても SubjectNotInTriggerException を投げる。"""
        with pytest.raises(SubjectNotInTriggerException):
            trigger.person_as(kind)

    @pytest.mark.parametrize("trigger", _TRIGGERS_WITHOUT_PEOPLE)
    def test_asking_the_item_raises_domain_exception(self, trigger: Trigger) -> None:
        """品物を尋ねると ItemNotInTriggerException を投げる。"""
        with pytest.raises(ItemNotInTriggerException):
            trigger.this_item()


class TestTriggersThatAreNotActions:
    """行為でないきっかけが、行う人も引数も答えず、倒れた理由を世界の出来事にすることを保証する。"""

    @pytest.mark.parametrize("trigger", _TRIGGERS_NOT_ACTIONS)
    def test_acting_person_is_no_one(self, trigger: Trigger) -> None:
        """acting_person は NoActingPerson を返す。"""
        assert trigger.acting_person() == NoActingPerson()

    @pytest.mark.parametrize("trigger", _TRIGGERS_NOT_ACTIONS)
    def test_asking_an_argument_raises_domain_exception(self, trigger: Trigger) -> None:
        """引数 message を尋ねると ArgumentNotInTriggerException を投げる。"""
        with pytest.raises(ArgumentNotInTriggerException):
            trigger.argument(_MESSAGE)

    @pytest.mark.parametrize("trigger", _TRIGGERS_NOT_ACTIONS)
    def test_fall_cause_is_a_world_happening(self, trigger: Trigger) -> None:
        """bob が傷ついた倒れた理由は WorldHappening。選ばれた人が bob の集団の決定でも同じ。"""
        assert trigger.fall_cause_for(_BOB) == WorldHappening()


class TestGroupDecisionResult:
    """GroupDecisionResult が、集団の決定で選ばれた人だけを答えることを保証する。"""

    def test_answers_the_chosen_person(self) -> None:
        """追放の投票で bob が選ばれたきっかけは、CHOSEN_BY_GROUP に bob を答える。"""
        result = GroupDecisionResult(_EXILE_VOTE, chosen=_BOB)

        assert result.person_as(SubjectKind.CHOSEN_BY_GROUP) == _BOB

    @pytest.mark.parametrize("kind", [k for k in SubjectKind if k is not SubjectKind.CHOSEN_BY_GROUP])
    def test_other_subjects_raise_domain_exception(self, kind: SubjectKind) -> None:
        """選ばれた人以外の主語を尋ねると SubjectNotInTriggerException を投げる。"""
        with pytest.raises(SubjectNotInTriggerException):
            GroupDecisionResult(_EXILE_VOTE, chosen=_BOB).person_as(kind)

    def test_asking_the_item_raises_domain_exception(self) -> None:
        """品物を尋ねると ItemNotInTriggerException を投げる。"""
        with pytest.raises(ItemNotInTriggerException):
            GroupDecisionResult(_EXILE_VOTE, chosen=_BOB).this_item()


class TestEachPersonOf:
    """EachPersonOf が「その人」を答え、それ以外は外のきっかけに任せることを保証する。"""

    def test_answers_the_person_being_looked_at(self) -> None:
        """alice の行為の中で carol を見ているとき、EACH_PERSON には carol を答える。"""
        trigger = EachPersonOf(ActionAttemptForTests(_ALICE), person=_CAROL)

        assert trigger.person_as(SubjectKind.EACH_PERSON) == _CAROL

    def test_other_subjects_come_from_the_outer_trigger(self) -> None:
        """alice が bob にした行為の中で carol を見ているとき、ACTOR は alice、TARGET は bob。"""
        trigger = EachPersonOf(ActionAttemptForTests(_ALICE, target=_BOB), person=_CAROL)

        assert trigger.person_as(SubjectKind.ACTOR) == _ALICE
        assert trigger.person_as(SubjectKind.TARGET) == _BOB

    def test_subject_the_outer_trigger_lacks_raises_domain_exception(self) -> None:
        """外のきっかけが答えない主語は、包んでも SubjectNotInTriggerException を投げる。"""
        trigger = EachPersonOf(WorldTimePassing(WorldTick(3)), person=_CAROL)

        with pytest.raises(SubjectNotInTriggerException):
            trigger.person_as(SubjectKind.ACTOR)

    def test_inner_person_wins_over_outer_person(self) -> None:
        """「その人」の中でさらに別の人を見るとき、EACH_PERSON は内側の人を答える。"""
        trigger = EachPersonOf(EachPersonOf(WorldTimePassing(WorldTick(3)), person=_BOB), person=_CAROL)

        assert trigger.person_as(SubjectKind.EACH_PERSON) == _CAROL

    def test_item_comes_from_the_outer_trigger(self) -> None:
        """ランタンを使う行為の中で carol を見ているとき、品物はランタン。"""
        trigger = EachPersonOf(ActionAttemptForTests(_ALICE, item=_LANTERN), person=_CAROL)

        assert trigger.this_item() == _LANTERN

    def test_acting_person_comes_from_the_outer_trigger(self) -> None:
        """alice の行為の中で carol を見ているとき、acting_person は carol ではなく alice。"""
        trigger = EachPersonOf(ActionAttemptForTests(_ALICE), person=_CAROL)

        assert trigger.acting_person() == _ALICE

    def test_acting_person_is_no_one_inside_a_trigger_without_one(self) -> None:
        """時間の経過の中で carol を見ているとき、acting_person は NoActingPerson。"""
        trigger = EachPersonOf(WorldTimePassing(WorldTick(3)), person=_CAROL)

        assert trigger.acting_person() == NoActingPerson()

    def test_argument_comes_from_the_outer_trigger(self) -> None:
        """引数 message に「助けて」を渡した行為の中で carol を見ているとき、message は「助けて」。"""
        outer = ActionAttemptForTests(_ALICE, arguments={_MESSAGE: TextArgumentValue("助けて")})
        trigger = EachPersonOf(outer, person=_CAROL)

        assert trigger.argument(_MESSAGE) == TextArgumentValue("助けて")

    def test_argument_the_outer_trigger_lacks_raises_domain_exception(self) -> None:
        """外のきっかけが答えない引数は、包んでも ArgumentNotInTriggerException を投げる。"""
        trigger = EachPersonOf(WorldTimePassing(WorldTick(3)), person=_CAROL)

        with pytest.raises(ArgumentNotInTriggerException):
            trigger.argument(_MESSAGE)

    def test_fall_cause_comes_from_the_outer_trigger(self) -> None:
        """alice の行為の中で carol を見ているとき、carol が傷ついた倒れた理由は alice に殴られたこと。"""
        trigger = EachPersonOf(ActionAttemptForTests(_ALICE), person=_CAROL)

        assert trigger.fall_cause_for(_CAROL) == StruckByPerson(_ALICE)
