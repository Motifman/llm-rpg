"""ItemSpec payload codec shared by SQLite repositories."""

from __future__ import annotations

import json
from typing import Any, Dict

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_effect import (
    CompositeItemEffect,
    ExpEffect,
    GoldEffect,
    HealEffect,
    ItemEffect,
    RecoverMpEffect,
)
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize


def item_spec_to_payload(spec: ItemSpec) -> Dict[str, Any]:
    return {
        "item_spec_id": int(spec.item_spec_id),
        "name": spec.name,
        "item_type": spec.item_type.value,
        "rarity": spec.rarity.value,
        "description": spec.description,
        "max_stack_size": int(spec.max_stack_size.value),
        "durability_max": spec.durability_max,
        "equipment_type": spec.equipment_type.value if spec.equipment_type else None,
        "is_placeable": spec.is_placeable,
        "placeable_object_type": spec.placeable_object_type,
        "consume_effect": (
            item_effect_to_payload(spec.consume_effect)
            if spec.consume_effect is not None
            else None
        ),
    }


def payload_to_item_spec(data: Dict[str, Any]) -> ItemSpec:
    eq_raw = data.get("equipment_type")
    equipment_type = EquipmentType(eq_raw) if eq_raw else None
    return ItemSpec(
        item_spec_id=ItemSpecId(int(data["item_spec_id"])),
        name=str(data["name"]),
        item_type=ItemType(str(data["item_type"])),
        rarity=Rarity(str(data["rarity"])),
        description=str(data["description"]),
        max_stack_size=MaxStackSize(int(data["max_stack_size"])),
        durability_max=data.get("durability_max"),
        equipment_type=equipment_type,
        is_placeable=bool(data.get("is_placeable", False)),
        placeable_object_type=data.get("placeable_object_type"),
        consume_effect=payload_to_item_effect(data["consume_effect"])
        if data.get("consume_effect") is not None
        else None,
    )


def item_spec_to_json(spec: ItemSpec) -> str:
    return json.dumps(
        item_spec_to_payload(spec),
        ensure_ascii=True,
        separators=(",", ":"),
    )


def json_to_item_spec(payload_json: str) -> ItemSpec:
    return payload_to_item_spec(json.loads(payload_json))


def item_effect_to_payload(effect: ItemEffect) -> Dict[str, Any]:
    if isinstance(effect, HealEffect):
        return {"kind": "heal", "amount": int(effect.amount)}
    if isinstance(effect, RecoverMpEffect):
        return {"kind": "recover_mp", "amount": int(effect.amount)}
    if isinstance(effect, GoldEffect):
        return {"kind": "gold", "amount": int(effect.amount)}
    if isinstance(effect, ExpEffect):
        return {"kind": "exp", "amount": int(effect.amount)}
    if isinstance(effect, CompositeItemEffect):
        return {
            "kind": "composite",
            "effects": [item_effect_to_payload(sub) for sub in effect.effects],
        }
    raise TypeError(f"unsupported ItemEffect type: {type(effect).__name__}")


def payload_to_item_effect(data: Dict[str, Any]) -> ItemEffect:
    kind = str(data.get("kind", ""))
    if kind == "heal":
        return HealEffect(amount=int(data["amount"]))
    if kind == "recover_mp":
        return RecoverMpEffect(amount=int(data["amount"]))
    if kind == "gold":
        return GoldEffect(amount=int(data["amount"]))
    if kind == "exp":
        return ExpEffect(amount=int(data["amount"]))
    if kind == "composite":
        raw_effects = data.get("effects")
        if not isinstance(raw_effects, list):
            raise ValueError("composite effect requires effects list")
        return CompositeItemEffect(
            effects=tuple(payload_to_item_effect(sub) for sub in raw_effects)
        )
    raise ValueError(f"unknown consume_effect kind: {kind}")


__all__ = [
    "item_spec_to_payload",
    "payload_to_item_spec",
    "item_spec_to_json",
    "json_to_item_spec",
]
