from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.character import (
    GroupDeclaration,
    GroupingDeclaration,
    MembershipVisibility,
    NoSharedDescription,
)
from ai_rpg_world.game_world.domain.value_object import DisplayName, GroupId, GroupingId


def _grouping(changes: bool) -> GroupingDeclaration:
    return GroupingDeclaration(
        grouping_id=GroupingId("camp"),
        name=DisplayName("陣営"),
        visibility=MembershipVisibility.SELF_ONLY,
        changes=changes,
    )


def _group(grouping: GroupingDeclaration) -> GroupDeclaration:
    return GroupDeclaration(
        group_id=GroupId("wolves"),
        grouping=grouping,
        name=DisplayName("人狼"),
        members_know_each_other=True,
        shared_description=NoSharedDescription(),
    )


class TestMembershipVisibility:
    """MembershipVisibility が、所属を誰に見せるかの 3 段階だけを表すことを保証する。"""

    def test_has_exactly_everyone_self_only_and_nobody(self) -> None:
        """所属を見せる先は EVERYONE / SELF_ONLY / NOBODY の 3 つで、ほかには無い。"""
        assert {visibility.name for visibility in MembershipVisibility} == {"EVERYONE", "SELF_ONLY", "NOBODY"}


class TestMembersCanChange:
    """GroupDeclaration.members_can_change が、所属する分け方の changes を答えることを保証する。"""

    @pytest.mark.parametrize("changes", [True, False])
    def test_answers_changes_of_its_grouping(self, changes: bool) -> None:
        """分け方の changes が真なら真を、偽なら偽を答える。"""
        group = _group(_grouping(changes=changes))

        assert group.members_can_change() is changes


class TestGroupDeclarationAsKey:
    """GroupDeclaration が、所属の記録 (members_of など) のキーとして使えることを保証する。"""

    def test_declarations_with_same_fields_are_equal_and_hash_alike(self) -> None:
        """同じ欄を持つ 2 つの GroupDeclaration は等しく、集合では 1 つにまとまる。"""
        first = _group(_grouping(changes=False))
        second = _group(_grouping(changes=False))

        assert first == second
        assert len({first, second}) == 1
