from __future__ import annotations

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure, NoText
from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.membership_condition import IsMemberCondition
from ai_rpg_world.game_world.domain.condition.subject import Actor, NamedPerson, SubjectKind, Target
from ai_rpg_world.game_world.domain.declaration.character.character_declaration import CharacterDeclaration
from ai_rpg_world.game_world.domain.declaration.character.group_declaration import (
    GroupDeclaration,
    MembershipVisibility,
)
from ai_rpg_world.game_world.domain.value_object import DescriptionText, SpotId
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from tests.game_world.domain.condition._builders import ALICE, BOB, group, text, world
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.declarations_for_tests import HappeningForTests

_ROOT = ConditionPath.root()
_ALICE_TO_BOB = ActionAttemptForTests(actor_id=ALICE, target=BOB)
_NOT_A_WOLF = text("狼ではない")


def _wolves(visibility: MembershipVisibility, *, members_know_each_other: bool = False) -> GroupDeclaration:
    return group("wolves", visibility=visibility, members_know_each_other=members_know_each_other, grouping_id="role")


def _is_wolf(who: Actor | Target, wolves: GroupDeclaration) -> IsMemberCondition:
    return IsMemberCondition(who=who, group=wolves, failure_text=_NOT_A_WOLF)


class TestIsMemberHolds:
    """IsMemberCondition が facts.membership() の所属で真偽を決めることを保証する。"""

    def test_member_holds(self) -> None:
        """bob が狼なら、相手 (bob) が狼である条件は真で、failure_reason は None。"""
        wolves = _wolves(MembershipVisibility.SELF_ONLY)
        a_world = world()
        a_world.membership.join(BOB, wolves)

        condition = _is_wolf(Target(), wolves)

        assert condition.holds(a_world.facts(), _ALICE_TO_BOB)
        assert condition.failure_reason(a_world.facts(), _ALICE_TO_BOB) is None

    def test_requires_its_subject(self) -> None:
        """相手が狼である条件は TARGET を要る。"""
        assert _is_wolf(Target(), _wolves(MembershipVisibility.EVERYONE)).requirements().subjects == frozenset(
            {SubjectKind.TARGET}
        )


class TestHiddenMembership:
    """IsMemberCondition が、行う人に知りえない所属を見て偽になったときだけ HiddenFailure を返すことを保証する。"""

    def test_other_persons_self_only_membership_is_hidden(self) -> None:
        """村人の alice が、bob の SELF_ONLY の所属 (狼) を見る前提で偽になると、文の無い HiddenFailure を返す。"""
        condition = _is_wolf(Target(), _wolves(MembershipVisibility.SELF_ONLY))

        assert condition.failure_reason(world().facts(), _ALICE_TO_BOB) == HiddenFailure(failed_part=_ROOT)

    def test_own_self_only_membership_is_told(self) -> None:
        """alice が自分の SELF_ONLY の所属を見る前提で偽になると、文つきの FailureReason を返す。"""
        condition = _is_wolf(Actor(), _wolves(MembershipVisibility.SELF_ONLY))

        assert condition.failure_reason(world().facts(), _ALICE_TO_BOB) == FailureReason(
            failed_part=_ROOT, text=_NOT_A_WOLF.about({})
        )

    def test_membership_visible_to_everyone_is_told(self) -> None:
        """EVERYONE の分け方の所属なら、他人の所属を見て偽になっても FailureReason を返す。"""
        condition = _is_wolf(Target(), _wolves(MembershipVisibility.EVERYONE))

        assert condition.failure_reason(world().facts(), _ALICE_TO_BOB) == FailureReason(
            failed_part=_ROOT, text=_NOT_A_WOLF.about({})
        )

    def test_fellow_member_who_knows_the_others_is_told(self) -> None:
        """members_know_each_other の狼に alice が入っていれば、bob が狼でないことを知りうるので FailureReason を返す。"""
        wolves = _wolves(MembershipVisibility.NOBODY, members_know_each_other=True)
        a_world = world()
        a_world.membership.join(ALICE, wolves)

        assert _is_wolf(Target(), wolves).failure_reason(a_world.facts(), _ALICE_TO_BOB) == FailureReason(
            failed_part=_ROOT, text=_NOT_A_WOLF.about({})
        )

    def test_outsider_of_a_group_that_knows_each_other_is_hidden(self) -> None:
        """members_know_each_other の狼でも、alice が入っていなければ bob の所属は知りえず HiddenFailure を返す。"""
        wolves = _wolves(MembershipVisibility.NOBODY, members_know_each_other=True)

        assert _is_wolf(Target(), wolves).failure_reason(world().facts(), _ALICE_TO_BOB) == HiddenFailure(
            failed_part=_ROOT
        )

    def test_own_membership_nobody_knows_is_hidden(self) -> None:
        """NOBODY の分け方では、alice が自分の所属を見る前提でも知りえず HiddenFailure を返す。"""
        condition = _is_wolf(Actor(), _wolves(MembershipVisibility.NOBODY))

        assert condition.failure_reason(world().facts(), _ALICE_TO_BOB) == HiddenFailure(failed_part=_ROOT)

    def test_happening_trigger_does_not_hide(self) -> None:
        """出来事のきっかけでは、知りえない所属を見て偽になっても HiddenFailure にせず FailureReason を返す。"""
        wolves = _wolves(MembershipVisibility.NOBODY)
        condition = IsMemberCondition(who=_named_bob(), group=wolves, failure_text=_NOT_A_WOLF)
        happening = HappeningFired(HappeningForTests(HappeningId("dawn")))

        assert condition.failure_reason(world().facts(), happening) == FailureReason(
            failed_part=_ROOT, text=_NOT_A_WOLF.about({})
        )


def _named_bob() -> NamedPerson:
    return NamedPerson(
        CharacterDeclaration(
            person_id=BOB,
            appearance=DescriptionText("背の高い男"),
            spawn_spot=SpotId("square"),
            initial_items=(),
            initial_held=(),
            initial_groups=(),
            knows_at_start=(),
        )
    )


class TestMayHideMembership:
    """IsMemberCondition が、行う人に所属が伏せられうるかを requirements() で答えることを保証する。"""

    def test_everyone_visible_membership_is_never_hidden(self) -> None:
        """誰にでも見える (EVERYONE) 分け方の所属は、相手のものでも伏せられない。"""
        assert not _is_wolf(Target(), _wolves(MembershipVisibility.EVERYONE)).requirements().may_hide_membership

    def test_own_self_only_membership_is_not_hidden(self) -> None:
        """本人だけに見える (SELF_ONLY) 分け方でも、行う人自身 (Actor) の所属は伏せられない。"""
        assert not _is_wolf(Actor(), _wolves(MembershipVisibility.SELF_ONLY)).requirements().may_hide_membership

    def test_others_self_only_membership_may_be_hidden(self) -> None:
        """SELF_ONLY の分け方で相手 (Target) の所属を見ると、伏せられうる。"""
        assert _is_wolf(Target(), _wolves(MembershipVisibility.SELF_ONLY)).requirements().may_hide_membership

    def test_nobody_visible_membership_may_be_hidden_even_for_oneself(self) -> None:
        """誰にも見えない (NOBODY) 分け方なら、行う人自身の所属でも伏せられうる。"""
        assert _is_wolf(Actor(), _wolves(MembershipVisibility.NOBODY)).requirements().may_hide_membership

    def test_members_who_know_each_other_may_still_hide_from_outsiders(self) -> None:
        """仲間どうしが知る集団でも、SELF_ONLY の相手の所属は仲間でない人には伏せられうる。"""
        wolves = _wolves(MembershipVisibility.SELF_ONLY, members_know_each_other=True)

        assert _is_wolf(Target(), wolves).requirements().may_hide_membership
