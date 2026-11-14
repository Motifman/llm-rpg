from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.world_records.world_flags import FlagPosition, WorldFlagsMemento
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    distinct_items,
    exact_fields,
    flag_id_from_json,
    json_bool,
    world_id_from_json,
)


def _position_from_json(raw: object) -> FlagPosition:
    fields = exact_fields(raw, ("flag", "raised"))
    return FlagPosition(flag_id_from_json(fields["flag"]), json_bool(fields["raised"]))


@final
class WorldFlagsCodec:
    kind = "world_flags"
    version = 1
    memento_type = WorldFlagsMemento

    def to_json(self, memento: WorldFlagsMemento) -> object:
        return {
            "world_id": memento.world_id.value,
            "positions": [
                {"flag": position.flag.value, "raised": position.raised}
                for position in sorted(memento.positions, key=lambda position: position.flag.value)
            ],
        }

    def from_json(self, raw: object) -> WorldFlagsMemento:
        fields = exact_fields(raw, ("world_id", "positions"))
        return WorldFlagsMemento(
            world_id=world_id_from_json(fields["world_id"]),
            positions=distinct_items(fields["positions"], _position_from_json),
        )
