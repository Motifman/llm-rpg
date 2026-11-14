from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.objects_and_items import GroundItemsMemento, ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import SpotId
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import exact_fields, json_str, ordered_items


def _item_from_json(raw: object) -> ItemInstanceId:
    return ItemInstanceId(json_str(raw))


@final
class GroundItemsCodec:
    kind = "ground_items"
    version = 1
    memento_type = GroundItemsMemento

    def to_json(self, memento: GroundItemsMemento) -> object:
        return {"spot_id": memento.spot_id.value, "items": [item.value for item in memento.items]}

    def from_json(self, raw: object) -> GroundItemsMemento:
        fields = exact_fields(raw, ("spot_id", "items"))
        return GroundItemsMemento(
            spot_id=SpotId(json_str(fields["spot_id"])),
            items=ordered_items(fields["items"], _item_from_json),
        )
