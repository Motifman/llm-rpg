from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.trigger import (
    EachPersonOf,
    GroupDecisionResult,
    WorldTimePassing,
)
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import (
    Actor,
    ChosenByGroup,
    EachPerson,
    NamedPerson,
    Subject,
    SubjectKind,
    Target,
    ThisItem,
)
from ai_rpg_world.game_world.domain.declaration.character.character_declaration import CharacterDeclaration
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.exception.trigger_exception import (
    ItemNotInTriggerException,
    SubjectNotInTriggerException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    GroupDecisionId,
    PersonId,
    SpotId,
    WorldTick,
)
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests

_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_CAROL = PersonId("carol")
_DAVE = PersonId("dave")
_LANTERN = ItemInstanceId("lantern-1")
_DAVE_DECLARED = CharacterDeclaration(
    person_id=_DAVE,
    appearance=DescriptionText("背の高い男"),
    spawn_spot=SpotId("square"),
    initial_items=(),
    initial_held=(),
    initial_groups=(),
    knows_at_start=(),
)
_EXILE_VOTE = GroupDecisionDeclaration(
    decision_id=GroupDecisionId("exile_vote"),
    name=DisplayName("追放の投票"),
    abstain_allowed=True,
    reveals_ballots=False,
)


class TestPersonIn:
    """Subject.person_in が、きっかけから主語の指す人を 1 人に決めることを保証する。"""

    def test_actor_is_the_person_who_acted(self) -> None:
        """alice が bob にした行為では、Actor は alice。"""
        assert Actor().person_in(ActionAttemptForTests(_ALICE, target=_BOB)) == _ALICE

    def test_target_is_the_person_acted_on(self) -> None:
        """alice が bob にした行為では、Target は bob。"""
        assert Target().person_in(ActionAttemptForTests(_ALICE, target=_BOB)) == _BOB

    def test_chosen_by_group_is_the_person_the_group_chose(self) -> None:
        """追放の投票で bob が選ばれたとき、ChosenByGroup は bob。"""
        assert ChosenByGroup().person_in(GroupDecisionResult(_EXILE_VOTE, chosen=_BOB)) == _BOB

    def test_each_person_is_the_person_being_looked_at(self) -> None:
        """時間の経過の中で carol を見ているとき、EachPerson は carol。"""
        assert EachPerson().person_in(EachPersonOf(WorldTimePassing(WorldTick(3)), person=_CAROL)) == _CAROL

    def test_named_person_is_the_declared_character_whatever_the_trigger(self) -> None:
        """宣言で dave を名指しした NamedPerson は、行為の中でも時間の経過の中でも dave。"""
        named = NamedPerson(_DAVE_DECLARED)

        assert named.person_in(ActionAttemptForTests(_ALICE)) == _DAVE
        assert named.person_in(WorldTimePassing(WorldTick(3))) == _DAVE

    def test_actor_without_an_action_raises_domain_exception(self) -> None:
        """時間の経過のきっかけで Actor を尋ねると SubjectNotInTriggerException を投げる。"""
        with pytest.raises(SubjectNotInTriggerException):
            Actor().person_in(WorldTimePassing(WorldTick(3)))


class TestRequirements:
    """Subject.requirements が、その主語の種類だけを要ると答えることを保証する。"""

    @pytest.mark.parametrize(
        ("subject", "kind"),
        [
            (Actor(), SubjectKind.ACTOR),
            (Target(), SubjectKind.TARGET),
            (ChosenByGroup(), SubjectKind.CHOSEN_BY_GROUP),
            (NamedPerson(_DAVE_DECLARED), SubjectKind.NAMED_PERSON),
            (EachPerson(), SubjectKind.EACH_PERSON),
        ],
    )
    def test_requires_only_its_own_kind(self, subject: Subject, kind: SubjectKind) -> None:
        """主語は自分の種類だけを要り、偶然・引数・待つ旗は要らない。"""
        assert subject.requirements() == Requirements(
            subjects=frozenset({kind}),
            uses_chance=False,
            uses_action_arguments=False,
            waits_for_flags=frozenset(),
        )


class TestThisItem:
    """ThisItem.item_in が、きっかけの品物を答えることを保証する。"""

    def test_item_of_the_action(self) -> None:
        """alice がランタンを使う行為では、ThisItem はランタン。"""
        assert ThisItem().item_in(ActionAttemptForTests(_ALICE, item=_LANTERN)) == _LANTERN

    def test_trigger_without_item_raises_domain_exception(self) -> None:
        """時間の経過のきっかけで ThisItem を尋ねると ItemNotInTriggerException を投げる。"""
        with pytest.raises(ItemNotInTriggerException):
            ThisItem().item_in(WorldTimePassing(WorldTick(3)))
