from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.character import (
    GroupDeclaration,
    GroupingDeclaration,
    MembershipVisibility,
    NoSharedDescription,
)
from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    MementoDoesNotMatchDesignException,
    RepeatedMementoKeyException,
)
from ai_rpg_world.game_world.domain.exception.person_exception import (
    AlreadyInAnotherGroupOfGroupingException,
    AlreadyInGroupException,
    GroupingDoesNotChangeException,
    NotInGroupException,
)
from ai_rpg_world.game_world.domain.person import (
    GroupMembership,
    GroupMembershipMemento,
    NotInAnyGroup,
    PersonGroupInGrouping,
    PersonJoinedGroupEvent,
    PersonLeftGroupEvent,
)
from ai_rpg_world.game_world.domain.value_object import DisplayName, GroupId, GroupingId, PersonId, WorldId
from tests.game_world.support.memento_for_tests import rebuilt_from_memento
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, spot

_WORLD = WorldId("island")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")


def _grouping(name: str, changes: bool = True) -> GroupingDeclaration:
    return GroupingDeclaration(
        grouping_id=GroupingId(name),
        name=DisplayName(name),
        visibility=MembershipVisibility.EVERYONE,
        changes=changes,
    )


def _group(name: str, grouping: GroupingDeclaration) -> GroupDeclaration:
    return GroupDeclaration(
        group_id=GroupId(name),
        grouping=grouping,
        name=DisplayName(name),
        members_know_each_other=False,
        shared_description=NoSharedDescription(),
    )


_TEAMS = _grouping("teams")
_RED = _group("red", _TEAMS)
_BLUE = _group("blue", _TEAMS)
_ROLES = _grouping("roles", changes=False)
_KEEPER = _group("keeper", _ROLES)
_CREW = _group("crew", _ROLES)


def _membership(initial: dict[PersonId, tuple[GroupDeclaration, ...]] | None = None) -> GroupMembership:
    return GroupMembership.start(_WORLD, {} if initial is None else initial)


class TestStart:
    """GroupMembership.start が最初の所属を入れて始めることを保証する。"""

    def test_initial_memberships_are_in_place_without_events(self) -> None:
        """最初の所属は、所属が変わらない分け方の集団でも入り、イベントをためない。"""
        membership = _membership({_ALICE: (_RED, _KEEPER), _BOB: (_CREW,)})

        assert membership.is_member(_ALICE, _RED)
        assert membership.is_member(_ALICE, _KEEPER)
        assert membership.members_of(_CREW) == frozenset({_BOB})
        assert membership.get_events() == []

    def test_keeps_the_world_as_its_id(self) -> None:
        """世界に 1 つの集約として、WorldId を持つ。"""
        assert _membership().world == _WORLD

    def test_two_initial_groups_of_one_grouping_raise_domain_exception(self) -> None:
        """同じ分け方の 2 つの集団を最初の所属に持つと AlreadyInAnotherGroupOfGroupingException を投げる。"""
        with pytest.raises(AlreadyInAnotherGroupOfGroupingException):
            _membership({_ALICE: (_RED, _BLUE)})


class TestJoin:
    """join が、分け方ごとに 1 つの集団へ人を入れることを保証する。"""

    def test_joining_makes_the_person_a_member_and_raises_event(self) -> None:
        """集団に入ると is_member と group_of に表れ、PersonJoinedGroupEvent をためる。"""
        membership = _membership()

        membership.join(_ALICE, _RED)

        assert membership.is_member(_ALICE, _RED)
        assert membership.group_of(_ALICE, _TEAMS) == GroupId("red")
        [event] = membership.get_events()
        assert isinstance(event, PersonJoinedGroupEvent)
        assert (event.world, event.person, event.group, event.grouping) == (
            _WORLD,
            _ALICE,
            GroupId("red"),
            GroupingId("teams"),
        )

    def test_joining_the_same_group_again_raises_domain_exception(self) -> None:
        """既に入っている集団に入ると AlreadyInGroupException を投げ、イベントをためない。"""
        membership = _membership({_ALICE: (_RED,)})

        with pytest.raises(AlreadyInGroupException):
            membership.join(_ALICE, _RED)
        assert membership.get_events() == []

    def test_joining_another_group_of_the_same_grouping_raises_domain_exception(self) -> None:
        """同じ分け方の別の集団に入ると AlreadyInAnotherGroupOfGroupingException を投げ、元の集団のまま。"""
        membership = _membership({_ALICE: (_RED,)})

        with pytest.raises(AlreadyInAnotherGroupOfGroupingException):
            membership.join(_ALICE, _BLUE)
        assert membership.group_of(_ALICE, _TEAMS) == GroupId("red")

    def test_joining_a_group_whose_grouping_does_not_change_raises_domain_exception(self) -> None:
        """所属が変わらない分け方 (changes が偽) の集団へは入れず、GroupingDoesNotChangeException を投げる。"""
        with pytest.raises(GroupingDoesNotChangeException):
            _membership().join(_ALICE, _KEEPER)


class TestLeave:
    """leave が集団から人を外すことを保証する。"""

    def test_leaving_removes_the_member_and_raises_event(self) -> None:
        """集団を抜けると members_of から外れ、group_of は NotInAnyGroup になり、PersonLeftGroupEvent をためる。"""
        membership = _membership({_ALICE: (_RED,), _BOB: (_RED,)})

        membership.leave(_ALICE, _RED)

        assert membership.members_of(_RED) == frozenset({_BOB})
        assert membership.group_of(_ALICE, _TEAMS) == NotInAnyGroup()
        [event] = membership.get_events()
        assert isinstance(event, PersonLeftGroupEvent)
        assert (event.world, event.person, event.group, event.grouping) == (
            _WORLD,
            _ALICE,
            GroupId("red"),
            GroupingId("teams"),
        )

    def test_leaving_then_joining_another_group_moves_the_person(self) -> None:
        """抜けてから同じ分け方の別の集団に入れる。"""
        membership = _membership({_ALICE: (_RED,)})

        membership.leave(_ALICE, _RED)
        membership.join(_ALICE, _BLUE)

        assert membership.group_of(_ALICE, _TEAMS) == GroupId("blue")

    def test_leaving_a_group_the_person_is_not_in_raises_domain_exception(self) -> None:
        """入っていない集団から抜けると NotInGroupException を投げる。"""
        membership = _membership({_ALICE: (_RED,)})

        with pytest.raises(NotInGroupException):
            membership.leave(_ALICE, _BLUE)

    def test_leaving_a_group_whose_grouping_does_not_change_raises_domain_exception(self) -> None:
        """所属が変わらない分け方の集団からは抜けられず、GroupingDoesNotChangeException を投げ、所属は残る。"""
        membership = _membership({_ALICE: (_KEEPER,)})

        with pytest.raises(GroupingDoesNotChangeException):
            membership.leave(_ALICE, _KEEPER)
        assert membership.is_member(_ALICE, _KEEPER)


class TestQueries:
    """所属の問い合わせが、所属の無い人にも答えることを保証する。"""

    def test_person_without_membership(self) -> None:
        """どこにも入っていない人は is_member が偽、group_of が NotInAnyGroup、誰もいない集団の members_of は空。"""
        membership = _membership()

        assert not membership.is_member(_ALICE, _RED)
        assert membership.group_of(_ALICE, _TEAMS) == NotInAnyGroup()
        assert membership.members_of(_RED) == frozenset()


_DESIGN = compose_world(
    nouns(
        spots=(spot("beach"),),
        characters=(character("alice", "beach"), character("bob", "beach")),
        groupings=(_TEAMS, _ROLES),
        groups=(_RED, _BLUE, _KEEPER, _CREW),
    )
)


def _memento(*groups: PersonGroupInGrouping) -> GroupMembershipMemento:
    return GroupMembershipMemento(world_id=_WORLD, groups=frozenset(groups))


class TestGroupMembershipMemento:
    """GroupMembership を memento から作り直すと、組分けごとの所属が元と同じになり、イベントは出ないことを保証する。"""

    def test_rebuilt_membership_answers_like_the_original(self) -> None:
        """alice が red と keeper、bob が blue に入ってから blue を抜けたあと作り直すと、memento も所属の答えも元と同じ。"""
        membership = _membership({_ALICE: (_RED, _KEEPER)})
        membership.join(_BOB, _BLUE)
        membership.leave(_BOB, _BLUE)

        rebuilt = rebuilt_from_memento(membership, _DESIGN.nouns)

        assert rebuilt.memento() == membership.memento()
        assert rebuilt.memento() != _membership().memento()
        assert rebuilt.world == _WORLD
        assert rebuilt.group_of(_ALICE, _TEAMS) == GroupId("red")
        assert rebuilt.group_of(_ALICE, _ROLES) == GroupId("keeper")
        assert rebuilt.group_of(_BOB, _TEAMS) == NotInAnyGroup()
        assert rebuilt.members_of(_RED) == frozenset({_ALICE})

    def test_rebuilding_records_no_event(self) -> None:
        """集団に入ったあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        membership = _membership()
        membership.join(_ALICE, _RED)

        assert rebuilt_from_memento(membership, _DESIGN.nouns).get_events() == []


class TestGroupMembershipMementoRefusals:
    """GroupMembership の memento が、宣言と食い違う所属や同じ組分けの重なりを持つとき、作り直しを断ることを保証する。"""

    def test_group_not_declared_is_refused(self) -> None:
        """宣言に無い green に alice が入っている memento から作り直すと、UndeclaredNounException を投げる。"""
        memento = _memento(PersonGroupInGrouping(_ALICE, GroupingId("teams"), GroupId("green")))

        with pytest.raises(UndeclaredNounException):
            GroupMembership.from_memento(memento, _DESIGN.nouns)

    def test_person_not_declared_is_refused(self) -> None:
        """宣言に無い carol が red に入っている memento から作り直すと、UndeclaredNounException を投げる。"""
        memento = _memento(PersonGroupInGrouping(PersonId("carol"), GroupingId("teams"), GroupId("red")))

        with pytest.raises(UndeclaredNounException):
            GroupMembership.from_memento(memento, _DESIGN.nouns)

    def test_group_of_another_grouping_is_refused(self) -> None:
        """roles の集団 keeper を teams の所属として持つ memento から作り直すと、MementoDoesNotMatchDesignException を投げる。"""
        memento = _memento(PersonGroupInGrouping(_ALICE, GroupingId("teams"), GroupId("keeper")))

        with pytest.raises(MementoDoesNotMatchDesignException):
            GroupMembership.from_memento(memento, _DESIGN.nouns)

    def test_two_groups_of_one_grouping_for_a_person_is_refused(self) -> None:
        """alice が teams で red と blue の両方に入っている memento を作ると、RepeatedMementoKeyException を投げる。"""
        with pytest.raises(RepeatedMementoKeyException):
            _memento(
                PersonGroupInGrouping(_ALICE, GroupingId("teams"), GroupId("red")),
                PersonGroupInGrouping(_ALICE, GroupingId("teams"), GroupId("blue")),
            )
