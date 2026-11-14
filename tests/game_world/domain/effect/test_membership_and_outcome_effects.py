from __future__ import annotations

import pytest

from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.condition.subject import NamedPerson
from ai_rpg_world.game_world.domain.declaration.character.group_declaration import (
    GroupDeclaration,
    GroupingDeclaration,
    MembershipVisibility,
    NoSharedDescription,
)
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.effect.membership_and_outcome_effects import (
    JoinGroupEffect,
    LeaveGroupEffect,
    SetOutcomeEffect,
)
from ai_rpg_world.game_world.domain.exception.person_exception import OutcomeAlreadyDecidedException
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import OccupantNotPlacedException
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person import DeclaredOutcome
from ai_rpg_world.game_world.domain.value_object import DisplayName, GroupId, GroupingId, OutcomeId
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from tests.game_world.domain.effect._builders import ALICE, BOB, WORLD, character
from tests.game_world.domain.whereabouts._builders import spot
from tests.game_world.support.declarations_for_tests import HappeningForTests
from tests.game_world.support.world_in_memory import world_in_memory

_PLAZA = spot("plaza")
_QUAKE = HappeningFired(HappeningForTests(HappeningId("quake")))
_RESCUERS = GroupDeclaration(
    group_id=GroupId("rescuers"),
    grouping=GroupingDeclaration(
        grouping_id=GroupingId("duty"), name=DisplayName("役目"), visibility=MembershipVisibility.EVERYONE, changes=True
    ),
    name=DisplayName("救助隊"),
    members_know_each_other=True,
    shared_description=NoSharedDescription(),
)
_ESCAPED = OutcomeDeclaration(
    outcome_id=OutcomeId("escaped"),
    name=DisplayName("脱出"),
    announcement=TextWithUnassignedPeople("{person} は島を出た"),
)
_ALICE = NamedPerson(character(ALICE))


def _world() -> WorldSession:
    world = world_in_memory(world=WORLD, people=(ALICE, BOB), spots=(_PLAZA,))
    world.aggregates().whereabouts().place(PersonBody(ALICE), _PLAZA)
    world.aggregates().whereabouts().place(PersonBody(BOB), _PLAZA)
    return world


class TestGroupEffects:
    """JoinGroupEffect と LeaveGroupEffect が、GroupMembership に集団への出入りを頼むことを保証する。"""

    def test_join_then_leave_group(self) -> None:
        """Alice を救助隊に入れると仲間になり、抜けさせると仲間でなくなる。"""
        world = _world()

        JoinGroupEffect(_ALICE, _RESCUERS).apply(world.facts(), world.aggregates(), _QUAKE)
        joined = world.aggregates().membership().is_member(ALICE, _RESCUERS)
        LeaveGroupEffect(_ALICE, _RESCUERS).apply(world.facts(), world.aggregates(), _QUAKE)

        assert joined
        assert not world.aggregates().membership().is_member(ALICE, _RESCUERS)


class TestSetOutcomeEffect:
    """SetOutcomeEffect が、その人の結末を決め、体を世界から外すことを保証する。"""

    def test_decides_outcome_and_removes_body(self) -> None:
        """Alice の結末を「脱出」にすると、結末が決まり、Alice の体は居場所を失い、Bob は広場に残る。"""
        world = _world()

        SetOutcomeEffect(_ALICE, _ESCAPED).apply(world.facts(), world.aggregates(), _QUAKE)

        assert world.aggregates().outcomes().outcome_of(ALICE) == DeclaredOutcome(_ESCAPED)
        with pytest.raises(OccupantNotPlacedException):
            world.aggregates().whereabouts().location_of(PersonBody(ALICE))
        assert world.aggregates().whereabouts().is_at(PersonBody(BOB), _PLAZA)

    def test_second_outcome_is_refused(self) -> None:
        """結末が決まった Alice にもう一度結末を決めると、PersonOutcomes が OutcomeAlreadyDecidedException で断る。"""
        world = _world()
        SetOutcomeEffect(_ALICE, _ESCAPED).apply(world.facts(), world.aggregates(), _QUAKE)

        with pytest.raises(OutcomeAlreadyDecidedException):
            SetOutcomeEffect(_ALICE, _ESCAPED).apply(world.facts(), world.aggregates(), _QUAKE)
