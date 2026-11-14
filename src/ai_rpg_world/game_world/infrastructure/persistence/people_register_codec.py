from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.people.people_register import PeopleRegisterMemento, PersonName
from ai_rpg_world.game_world.domain.value_object import DisplayName
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    distinct_items,
    exact_fields,
    json_str,
    person_id_from_json,
    world_id_from_json,
)


def _name_from_json(raw: object) -> PersonName:
    fields = exact_fields(raw, ("person", "name"))
    return PersonName(person_id_from_json(fields["person"]), DisplayName(json_str(fields["name"])))


@final
class PeopleRegisterCodec:
    kind = "people_register"
    version = 1
    memento_type = PeopleRegisterMemento

    def to_json(self, memento: PeopleRegisterMemento) -> object:
        return {
            "world_id": memento.world_id.value,
            "names": [
                {"person": entry.person.value, "name": entry.name.text}
                for entry in sorted(memento.names, key=lambda entry: entry.person.value)
            ],
        }

    def from_json(self, raw: object) -> PeopleRegisterMemento:
        fields = exact_fields(raw, ("world_id", "names"))
        return PeopleRegisterMemento(
            world_id=world_id_from_json(fields["world_id"]),
            names=distinct_items(fields["names"], _name_from_json),
        )
