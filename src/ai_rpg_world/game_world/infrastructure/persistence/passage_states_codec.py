from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.value_object import PassageId, PassageStateName
from ai_rpg_world.game_world.domain.whereabouts import PassageCondition, PassagePresence, PassageStatesMemento
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    distinct_items,
    enum_from_json,
    enum_to_json,
    exact_fields,
    json_str,
    world_id_from_json,
)


def _condition_from_json(raw: object) -> PassageCondition:
    fields = exact_fields(raw, ("passage", "state", "presence"))
    return PassageCondition(
        PassageId(json_str(fields["passage"])),
        PassageStateName(json_str(fields["state"])),
        enum_from_json(fields["presence"], PassagePresence),
    )


@final
class PassageStatesCodec:
    kind = "passage_states"
    version = 1
    memento_type = PassageStatesMemento

    def to_json(self, memento: PassageStatesMemento) -> object:
        return {
            "world_id": memento.world_id.value,
            "passages": [
                {
                    "passage": condition.passage.value,
                    "state": condition.state.value,
                    "presence": enum_to_json(condition.presence),
                }
                for condition in sorted(memento.passages, key=lambda condition: condition.passage.value)
            ],
        }

    def from_json(self, raw: object) -> PassageStatesMemento:
        fields = exact_fields(raw, ("world_id", "passages"))
        return PassageStatesMemento(
            world_id=world_id_from_json(fields["world_id"]),
            passages=distinct_items(fields["passages"], _condition_from_json),
        )
