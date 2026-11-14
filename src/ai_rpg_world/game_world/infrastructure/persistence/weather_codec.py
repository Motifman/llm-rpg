from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.declaration.time_and_weather import WeatherState, WeatherType
from ai_rpg_world.game_world.domain.world_progress import WeatherMemento
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    enum_from_json,
    enum_to_json,
    exact_fields,
    world_id_from_json,
)


@final
class WeatherCodec:
    kind = "weather"
    version = 1
    memento_type = WeatherMemento

    def to_json(self, memento: WeatherMemento) -> object:
        return {"world_id": memento.world_id.value, "current": {"type": enum_to_json(memento.current.type)}}

    def from_json(self, raw: object) -> WeatherMemento:
        fields = exact_fields(raw, ("world_id", "current"))
        current = exact_fields(fields["current"], ("type",))
        return WeatherMemento(
            world_id=world_id_from_json(fields["world_id"]),
            current=WeatherState(enum_from_json(current["type"], WeatherType)),
        )
