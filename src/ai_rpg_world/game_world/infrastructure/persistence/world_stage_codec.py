from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.value_object import WorldStageId
from ai_rpg_world.game_world.domain.world_progress import WorldStageMemento
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    exact_fields,
    json_str,
    world_id_from_json,
    world_tick_from_json,
)


@final
class WorldStageCodec:
    kind = "world_stage"
    version = 1
    memento_type = WorldStageMemento

    def to_json(self, memento: WorldStageMemento) -> object:
        return {
            "world_id": memento.world_id.value,
            "current": memento.current.value,
            "entered_at": memento.entered_at.value,
        }

    def from_json(self, raw: object) -> WorldStageMemento:
        fields = exact_fields(raw, ("world_id", "current", "entered_at"))
        return WorldStageMemento(
            world_id=world_id_from_json(fields["world_id"]),
            current=WorldStageId(json_str(fields["current"])),
            entered_at=world_tick_from_json(fields["entered_at"]),
        )
