from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.objects_and_items import ObjectStateKeyValue, ObjectStateMemento, ObjectStockLevel
from ai_rpg_world.game_world.domain.value_object import ObjectId
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    distinct_items,
    exact_fields,
    json_bool,
    json_str,
    world_tick_from_json,
)
from ai_rpg_world.game_world.infrastructure.persistence.state_value_json import (
    STATE_VALUE,
    count_from_json,
    state_key_from_json,
)


def _key_value_from_json(raw: object) -> ObjectStateKeyValue:
    fields = exact_fields(raw, ("key", "value"))
    return ObjectStateKeyValue(state_key_from_json(fields["key"]), STATE_VALUE.from_json(fields["value"]))


def _stock_level_from_json(raw: object) -> ObjectStockLevel:
    fields = exact_fields(raw, ("key", "amount", "counted_from"))
    return ObjectStockLevel(
        state_key_from_json(fields["key"]),
        count_from_json(fields["amount"]),
        world_tick_from_json(fields["counted_from"]),
    )


@final
class ObjectStateCodec:
    kind = "object_state"
    version = 1
    memento_type = ObjectStateMemento

    def to_json(self, memento: ObjectStateMemento) -> object:
        return {
            "object_id": memento.object_id.value,
            "values": [
                {"key": key_value.key.value, "value": STATE_VALUE.to_json(key_value.value)}
                for key_value in sorted(memento.values, key=lambda key_value: key_value.key.value)
            ],
            "stock_levels": [
                {"key": level.key.value, "amount": level.amount.value, "counted_from": level.counted_from.value}
                for level in sorted(memento.stock_levels, key=lambda level: level.key.value)
            ],
            "revealed": memento.revealed,
        }

    def from_json(self, raw: object) -> ObjectStateMemento:
        fields = exact_fields(raw, ("object_id", "values", "stock_levels", "revealed"))
        return ObjectStateMemento(
            object_id=ObjectId(json_str(fields["object_id"])),
            values=distinct_items(fields["values"], _key_value_from_json),
            stock_levels=distinct_items(fields["stock_levels"], _stock_level_from_json),
            revealed=json_bool(fields["revealed"]),
        )
