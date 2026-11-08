from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.character.group_declaration import (
    GroupDeclaration,
    GroupingDeclaration,
    MembershipVisibility,
    NoSharedDescription,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person import PersonVitals
from ai_rpg_world.game_world.domain.value_object import (
    DisplayName,
    GroupId,
    GroupingId,
    HitPoints,
    PersonId,
    WorldId,
)
from tests.game_world.support.world_in_memory import WorldInMemory

WORLD = WorldId("village")
ALICE = PersonId("alice")
BOB = PersonId("bob")
CAROL = PersonId("carol")


def text(template: str) -> TextWithUnassignedPeople:
    return TextWithUnassignedPeople(template)


def vitals(person: PersonId) -> PersonVitals:
    return PersonVitals.start(person, HitPoints(current=5, maximum=5))


def world(*, people: tuple[PersonId, ...] = (ALICE, BOB, CAROL), fractions: tuple[float, ...] = ()) -> WorldInMemory:
    return WorldInMemory(
        world=WORLD,
        people=people,
        vitals=tuple(vitals(person) for person in people),
        fractions=fractions,
    )


def group(
    group_id: str,
    *,
    visibility: MembershipVisibility,
    members_know_each_other: bool = False,
    grouping_id: str = "side",
) -> GroupDeclaration:
    return GroupDeclaration(
        group_id=GroupId(group_id),
        grouping=GroupingDeclaration(
            grouping_id=GroupingId(grouping_id),
            name=DisplayName(grouping_id),
            visibility=visibility,
            changes=True,
        ),
        name=DisplayName(group_id),
        members_know_each_other=members_know_each_other,
        shared_description=NoSharedDescription(),
    )
