"""Helpers for normalized item spec persistence."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

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


def build_item_spec(*, row: object, effect_rows: Iterable[object]) -> ItemSpec:
    rows = list(effect_rows)
    effect = _build_effect_tree(rows)
    equipment_type = row["equipment_type"]
    return ItemSpec(
        item_spec_id=ItemSpecId(int(row["item_spec_id"])),
        name=str(row["name"]),
        item_type=ItemType(str(row["item_type"])),
        rarity=Rarity(str(row["rarity"])),
        description=str(row["description"]),
        max_stack_size=MaxStackSize(int(row["max_stack_size"])),
        durability_max=row["durability_max"],
        equipment_type=None if equipment_type is None else EquipmentType(str(equipment_type)),
        is_placeable=bool(row["is_placeable"]),
        placeable_object_type=row["placeable_object_type"],
        consume_effect=effect,
    )


def flatten_item_effect(effect: ItemEffect | None) -> list[tuple[int, int | None, int, str, int | None]]:
    if effect is None:
        return []
    rows: list[tuple[int, int | None, int, str, int | None]] = []
    next_id = 1

    def visit(node: ItemEffect, parent_id: int | None, order: int) -> int:
        nonlocal next_id
        current_id = next_id
        next_id += 1
        kind, amount = _effect_kind_and_amount(node)
        rows.append((current_id, parent_id, order, kind, amount))
        if isinstance(node, CompositeItemEffect):
            for idx, child in enumerate(node.effects):
                visit(child, current_id, idx)
        return current_id

    visit(effect, None, 0)
    return rows


def item_spec_to_payload(item_spec: ItemSpec) -> dict[str, Any]:
    return {
        "item_spec_id": int(item_spec.item_spec_id),
        "name": item_spec.name,
        "item_type": item_spec.item_type.value,
        "rarity": item_spec.rarity.value,
        "description": item_spec.description,
        "max_stack_size": int(item_spec.max_stack_size.value),
        "durability_max": item_spec.durability_max,
        "equipment_type": (
            None if item_spec.equipment_type is None else item_spec.equipment_type.value
        ),
        "is_placeable": item_spec.is_placeable,
        "placeable_object_type": item_spec.placeable_object_type,
        "consume_effect": _effect_to_payload(item_spec.consume_effect),
    }


def payload_to_item_spec(payload: dict[str, Any]) -> ItemSpec:
    equipment_type = payload.get("equipment_type")
    return ItemSpec(
        item_spec_id=ItemSpecId(int(payload["item_spec_id"])),
        name=str(payload["name"]),
        item_type=ItemType(str(payload["item_type"])),
        rarity=Rarity(str(payload["rarity"])),
        description=str(payload.get("description", "")),
        max_stack_size=MaxStackSize(int(payload.get("max_stack_size", 1))),
        durability_max=payload.get("durability_max"),
        equipment_type=(
            None if equipment_type is None else EquipmentType(str(equipment_type))
        ),
        is_placeable=bool(payload.get("is_placeable", False)),
        placeable_object_type=payload.get("placeable_object_type"),
        consume_effect=_payload_to_effect(payload.get("consume_effect")),
    )


def _build_effect_tree(rows: list[object]) -> ItemEffect | None:
    if not rows:
        return None
    by_parent: dict[int | None, list[object]] = defaultdict(list)
    for row in rows:
        by_parent[row["parent_effect_id"]].append(row)
    for siblings in by_parent.values():
        siblings.sort(key=lambda row: int(row["effect_order"]))

    def build(row: object) -> ItemEffect:
        kind = str(row["effect_kind"])
        amount = row["amount"]
        if kind == "composite":
            return CompositeItemEffect(tuple(build(child) for child in by_parent.get(int(row["effect_id"]), [])))
        if kind == "heal":
            return HealEffect(int(amount))
        if kind == "recover_mp":
            return RecoverMpEffect(int(amount))
        if kind == "gold":
            return GoldEffect(int(amount))
        if kind == "exp":
            return ExpEffect(int(amount))
        raise ValueError(f"unknown item effect kind: {kind}")

    roots = by_parent.get(None, [])
    if not roots:
        return None
    return build(roots[0])


def _effect_kind_and_amount(effect: ItemEffect) -> tuple[str, int | None]:
    if isinstance(effect, CompositeItemEffect):
        return ("composite", None)
    if isinstance(effect, HealEffect):
        return ("heal", int(effect.amount))
    if isinstance(effect, RecoverMpEffect):
        return ("recover_mp", int(effect.amount))
    if isinstance(effect, GoldEffect):
        return ("gold", int(effect.amount))
    if isinstance(effect, ExpEffect):
        return ("exp", int(effect.amount))
    raise TypeError(f"unsupported ItemEffect type: {type(effect).__name__}")


def _effect_to_payload(effect: ItemEffect | None) -> dict[str, Any] | None:
    if effect is None:
        return None
    if isinstance(effect, CompositeItemEffect):
        return {
            "kind": "composite",
            "effects": [_effect_to_payload(child) for child in effect.effects],
        }
    kind, amount = _effect_kind_and_amount(effect)
    return {"kind": kind, "amount": amount}


def _payload_to_effect(payload: dict[str, Any] | None) -> ItemEffect | None:
    if payload is None:
        return None
    kind = str(payload["kind"])
    if kind == "composite":
        raw_children = payload.get("effects", [])
        return CompositeItemEffect(
            tuple(
                child
                for child in (_payload_to_effect(raw_child) for raw_child in raw_children)
                if child is not None
            )
        )
    amount = int(payload["amount"])
    if kind == "heal":
        return HealEffect(amount)
    if kind == "recover_mp":
        return RecoverMpEffect(amount)
    if kind == "gold":
        return GoldEffect(amount)
    if kind == "exp":
        return ExpEffect(amount)
    raise ValueError(f"unknown consume_effect kind: {kind}")


__all__ = [
    "build_item_spec",
    "flatten_item_effect",
    "item_spec_to_payload",
    "payload_to_item_spec",
]
