from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.objects_and_items import ItemInstanceId, ItemMemento, ItemStateKeyValue
from ai_rpg_world.game_world.domain.value_object import ItemSpecId
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    distinct_items,
    exact_fields,
    json_bool,
    json_str,
    world_tick_from_json,
)
from ai_rpg_world.game_world.infrastructure.persistence.state_value_json import STATE_VALUE, state_key_from_json


def _key_value_from_json(raw: object) -> ItemStateKeyValue:
    fields = exact_fields(raw, ("key", "value"))
    return ItemStateKeyValue(state_key_from_json(fields["key"]), STATE_VALUE.from_json(fields["value"]))


@final
class ItemCodec:
    kind = "item"
    version = 1
    memento_type = ItemMemento

    def to_json(self, memento: ItemMemento) -> object:
        return {
            "item_id": memento.item_id.value,
            "spec_id": memento.spec_id.value,
            "came_at": memento.came_at.value,
            "values": [
                {"key": key_value.key.value, "value": STATE_VALUE.to_json(key_value.value)}
                for key_value in sorted(memento.values, key=lambda key_value: key_value.key.value)
            ],
            "in_world": memento.in_world,
        }

    def from_json(self, raw: object) -> ItemMemento:
        fields = exact_fields(raw, ("item_id", "spec_id", "came_at", "values", "in_world"))
        return ItemMemento(
            item_id=ItemInstanceId(json_str(fields["item_id"])),
            spec_id=ItemSpecId(json_str(fields["spec_id"])),
            came_at=world_tick_from_json(fields["came_at"]),
            values=distinct_items(fields["values"], _key_value_from_json),
            in_world=json_bool(fields["in_world"]),
        )
