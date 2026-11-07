from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import final

from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, GroupId, GroupingId


class MembershipVisibility(Enum):
    EVERYONE = "EVERYONE"
    SELF_ONLY = "SELF_ONLY"
    NOBODY = "NOBODY"


@final
@dataclass(frozen=True)
class GroupingDeclaration:
    grouping_id: GroupingId
    name: DisplayName
    visibility: MembershipVisibility
    changes: bool


@final
@dataclass(frozen=True)
class NoSharedDescription:
    pass


@final
@dataclass(frozen=True)
class GroupDeclaration:
    group_id: GroupId
    grouping: GroupingDeclaration
    name: DisplayName
    members_know_each_other: bool
    shared_description: DescriptionText | NoSharedDescription

    def members_can_change(self) -> bool:
        return self.grouping.changes
