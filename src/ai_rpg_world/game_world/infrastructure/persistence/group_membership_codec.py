from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.person.group_membership import GroupMembershipMemento, PersonGroupInGrouping
from ai_rpg_world.game_world.domain.value_object import GroupId, GroupingId
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    distinct_items,
    exact_fields,
    json_str,
    person_id_from_json,
    world_id_from_json,
)


def _group_from_json(raw: object) -> PersonGroupInGrouping:
    fields = exact_fields(raw, ("person", "grouping", "group"))
    return PersonGroupInGrouping(
        person_id_from_json(fields["person"]),
        GroupingId(json_str(fields["grouping"])),
        GroupId(json_str(fields["group"])),
    )


@final
class GroupMembershipCodec:
    kind = "group_membership"
    version = 1
    memento_type = GroupMembershipMemento

    def to_json(self, memento: GroupMembershipMemento) -> object:
        return {
            "world_id": memento.world_id.value,
            "groups": [
                {"person": entry.person.value, "grouping": entry.grouping.value, "group": entry.group.value}
                for entry in sorted(memento.groups, key=lambda entry: (entry.person.value, entry.grouping.value))
            ],
        }

    def from_json(self, raw: object) -> GroupMembershipMemento:
        fields = exact_fields(raw, ("world_id", "groups"))
        return GroupMembershipMemento(
            world_id=world_id_from_json(fields["world_id"]),
            groups=distinct_items(fields["groups"], _group_from_json),
        )
