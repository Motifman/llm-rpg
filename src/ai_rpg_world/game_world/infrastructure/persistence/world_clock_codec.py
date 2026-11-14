from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.world_progress.world_clock import WorldClockMemento
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    exact_fields,
    world_id_from_json,
    world_tick_from_json,
)


@final
class WorldClockCodec:
    kind = "world_clock"
    version = 1
    memento_type = WorldClockMemento

    def to_json(self, memento: WorldClockMemento) -> object:
        return {"world_id": memento.world_id.value, "now": memento.now.value}

    def from_json(self, raw: object) -> WorldClockMemento:
        fields = exact_fields(raw, ("world_id", "now"))
        return WorldClockMemento(
            world_id=world_id_from_json(fields["world_id"]), now=world_tick_from_json(fields["now"])
        )
