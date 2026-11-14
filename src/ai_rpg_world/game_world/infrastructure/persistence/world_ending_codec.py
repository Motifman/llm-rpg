from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.world_progress import WorldEndingMemento
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import exact_fields, json_bool, world_id_from_json


@final
class WorldEndingCodec:
    kind = "world_ending"
    version = 1
    memento_type = WorldEndingMemento

    def to_json(self, memento: WorldEndingMemento) -> object:
        return {"world_id": memento.world_id.value, "ended": memento.ended}

    def from_json(self, raw: object) -> WorldEndingMemento:
        fields = exact_fields(raw, ("world_id", "ended"))
        return WorldEndingMemento(world_id=world_id_from_json(fields["world_id"]), ended=json_bool(fields["ended"]))
