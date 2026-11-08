from __future__ import annotations

import pytest

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
    ItemNotInTriggerException,
    SubjectNotInTriggerException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import DisplayName, GroupDecisionId, PersonId, WorldTick
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
