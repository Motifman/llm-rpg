from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.declaration.character import GroupDeclaration, GroupingDeclaration
from ai_rpg_world.game_world.domain.exception.person_exception import (
    AlreadyInAnotherGroupOfGroupingException,
    AlreadyInGroupException,
    GroupingDoesNotChangeException,
    NotInGroupException,
)
from ai_rpg_world.game_world.domain.value_object import GroupId, GroupingId, PersonId, WorldId


@final
@dataclass(frozen=True)
class NotInAnyGroup:
    pass


@dataclass(frozen=True, kw_only=True)
class GroupMembershipEvent(DomainEvent):
    world: WorldId
    person: PersonId
    group: GroupId
    grouping: GroupingId


@dataclass(frozen=True, kw_only=True)
class PersonJoinedGroupEvent(GroupMembershipEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class PersonLeftGroupEvent(GroupMembershipEvent):
    pass


class GroupMembership(AggregateRoot[GroupMembershipEvent]):
    def __init__(self, world: WorldId) -> None:
        super().__init__()
        self._world = world
        self._groups: dict[PersonId, dict[GroupingId, GroupId]] = {}

    @classmethod
    def start(cls, world: WorldId, initial: Mapping[PersonId, tuple[GroupDeclaration, ...]]) -> GroupMembership:
        membership = cls(world)
        for person, groups in initial.items():
            for group in groups:
                membership._enter(person, group)
        return membership

    @property
    def world(self) -> WorldId:
        return self._world

    def join(self, person: PersonId, group: GroupDeclaration) -> None:
        self._require_changes(group)
        self._enter(person, group)
        self._add(PersonJoinedGroupEvent, person, group)

    def leave(self, person: PersonId, group: GroupDeclaration) -> None:
        self._require_changes(group)
        if not self.is_member(person, group):
            raise NotInGroupException(f"{person.value} is not in {group.group_id.value}")
        del self._groups[person][group.grouping.grouping_id]
        self._add(PersonLeftGroupEvent, person, group)

    def is_member(self, person: PersonId, group: GroupDeclaration) -> bool:
        return self.group_of(person, group.grouping) == group.group_id

    def members_of(self, group: GroupDeclaration) -> frozenset[PersonId]:
        return frozenset(person for person in self._groups if self.is_member(person, group))

    def group_of(self, person: PersonId, grouping: GroupingDeclaration) -> GroupId | NotInAnyGroup:
        return self._groups.get(person, {}).get(grouping.grouping_id, NotInAnyGroup())

    def _enter(self, person: PersonId, group: GroupDeclaration) -> None:
        current = self.group_of(person, group.grouping)
        if current == group.group_id:
            raise AlreadyInGroupException(f"{person.value} is already in {group.group_id.value}")
        if isinstance(current, GroupId):
            raise AlreadyInAnotherGroupOfGroupingException(
                f"{person.value} is already in {current.value} of {group.grouping.grouping_id.value}"
            )
        self._groups.setdefault(person, {})[group.grouping.grouping_id] = group.group_id

    def _require_changes(self, group: GroupDeclaration) -> None:
        if not group.members_can_change():
            raise GroupingDoesNotChangeException(
                f"members of {group.group_id.value} do not change ({group.grouping.grouping_id.value})"
            )

    def _add(self, event_type: type[GroupMembershipEvent], person: PersonId, group: GroupDeclaration) -> None:
        self.add_event(
            event_type(
                **new_event_stamp(),
                world=self._world,
                person=person,
                group=group.group_id,
                grouping=group.grouping.grouping_id,
            )
        )
