from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.objects_and_items import (
    HeldItem,
    ItemInstanceId,
    PackedItem,
    PersonInventoryMemento,
)
from ai_rpg_world.game_world.domain.value_object import Capacity, Gold, HandsNeeded, ItemSpecId
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    exact_fields,
    json_int,
    json_str,
    ordered_items,
    person_id_from_json,
)


def _held_from_json(raw: object) -> HeldItem:
    fields = exact_fields(raw, ("item", "spec", "hands_needed"))
    return HeldItem(
        ItemInstanceId(json_str(fields["item"])),
        ItemSpecId(json_str(fields["spec"])),
        HandsNeeded(json_int(fields["hands_needed"])),
    )


def _packed_from_json(raw: object) -> PackedItem:
    fields = exact_fields(raw, ("item", "spec"))
    return PackedItem(ItemInstanceId(json_str(fields["item"])), ItemSpecId(json_str(fields["spec"])))


@final
class PersonInventoryCodec:
    kind = "person_inventory"
    version = 1
    memento_type = PersonInventoryMemento

    def to_json(self, memento: PersonInventoryMemento) -> object:
        return {
            "person_id": memento.person_id.value,
            "capacity": memento.capacity.value,
            "gold": memento.gold.value,
            "held": [
                {"item": held.item.value, "spec": held.spec.value, "hands_needed": held.hands_needed.value}
                for held in memento.held
            ],
            "packed": [{"item": packed.item.value, "spec": packed.spec.value} for packed in memento.packed],
        }

    def from_json(self, raw: object) -> PersonInventoryMemento:
        fields = exact_fields(raw, ("person_id", "capacity", "gold", "held", "packed"))
        return PersonInventoryMemento(
            person_id=person_id_from_json(fields["person_id"]),
            capacity=Capacity(json_int(fields["capacity"])),
            gold=Gold(json_int(fields["gold"])),
            held=ordered_items(fields["held"], _held_from_json),
            packed=ordered_items(fields["packed"], _packed_from_json),
        )
