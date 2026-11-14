from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.objects_and_items.item_serial_counter import ItemSerialCounterMemento
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import exact_fields, json_int, world_id_from_json


@final
class ItemSerialCounterCodec:
    kind = "item_serial_counter"
    version = 1
    memento_type = ItemSerialCounterMemento

    def to_json(self, memento: ItemSerialCounterMemento) -> object:
        return {"world_id": memento.world_id.value, "issued": memento.issued}

    def from_json(self, raw: object) -> ItemSerialCounterMemento:
        fields = exact_fields(raw, ("world_id", "issued"))
        return ItemSerialCounterMemento(
            world_id=world_id_from_json(fields["world_id"]), issued=json_int(fields["issued"])
        )
