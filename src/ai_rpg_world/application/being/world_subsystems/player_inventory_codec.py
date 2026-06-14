"""Player inventory subsystem codec (Phase 9-2b)。

各 player の ``PlayerInventoryAggregate`` を JSON 化:
- ``inventory_slots``: SlotId → ItemInstanceId | None (= 通常スロット)
- ``equipment_slots``: EquipmentSlotType → ItemInstanceId | None (= 装備)
- ``reserved_item_ids``: 予約中の ItemInstanceId 集合
- ``max_slots``: スロット最大数

restore は ``PlayerInventoryAggregate.restore_from_data`` (= public classmethod)
を経由するので、private 属性に触らずに済む。

NOTE: ItemInstance 自体 (= item の現状態 / decay / 個別属性) は本 codec の
対象外。Phase 9-3 の spot_interior / item_instances codec で別途扱う。
本 codec は **「どの ItemInstanceId をどの slot に持っているか」** だけを
保存する。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "player_inventory"
SCHEMA_VERSION = 1


class PlayerInventorySubsystemCodec(WorldSubsystemCodec):
    """各 player の inventory_slots / equipment_slots / reserved を JSON 化。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        repo = getattr(runtime, "_player_inventory_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._player_inventory_repo not found; "
                "PlayerInventorySubsystemCodec requires it"
            )
        entries: list[dict[str, Any]] = []
        for pid in runtime.get_player_ids():
            inv = repo.find_by_id(pid)
            if inv is None:
                continue
            # inventory_slots: SlotId -> ItemInstanceId | None
            inv_slot_list: list[dict[str, Any]] = []
            for slot_id, item_id in inv._inventory_slots.items():
                inv_slot_list.append(
                    {
                        "slot_id": int(slot_id.value),
                        "item_instance_id": (
                            int(item_id.value) if item_id is not None else None
                        ),
                    }
                )
            # equipment_slots: EquipmentSlotType -> ItemInstanceId | None
            eq_slot_list: list[dict[str, Any]] = []
            for eq_type, item_id in inv._equipment_slots.items():
                eq_slot_list.append(
                    {
                        "equipment_slot_type": eq_type.value,  # str (Enum)
                        "item_instance_id": (
                            int(item_id.value) if item_id is not None else None
                        ),
                    }
                )
            reserved_ids = [int(i.value) for i in inv._reserved_item_ids]
            entries.append(
                {
                    "player_id": int(pid.value),
                    "max_slots": int(inv._max_slots),
                    "inventory_slots": inv_slot_list,
                    "equipment_slots": eq_slot_list,
                    "reserved_item_ids": sorted(reserved_ids),  # 決定的順序
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "entries": entries,
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        from ai_rpg_world.domain.item.value_object.item_instance_id import (
            ItemInstanceId,
        )
        from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
            PlayerInventoryAggregate,
        )
        from ai_rpg_world.domain.player.enum.equipment_slot_type import (
            EquipmentSlotType,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId

        repo = getattr(runtime, "_player_inventory_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._player_inventory_repo not found; "
                "PlayerInventorySubsystemCodec requires it"
            )
        for entry in data.get("entries", []):
            pid = PlayerId(int(entry["player_id"]))
            max_slots = int(entry["max_slots"])
            # inventory_slots を Dict に組み直す
            inv_slots: dict[SlotId, Any] = {}
            for s in entry.get("inventory_slots", []):
                slot_id = SlotId(int(s["slot_id"]))
                item_raw = s.get("item_instance_id")
                inv_slots[slot_id] = (
                    ItemInstanceId(int(item_raw))
                    if item_raw is not None
                    else None
                )
            # equipment_slots
            eq_slots: dict[EquipmentSlotType, Any] = {}
            for s in entry.get("equipment_slots", []):
                eq_type = EquipmentSlotType(str(s["equipment_slot_type"]))
                item_raw = s.get("item_instance_id")
                eq_slots[eq_type] = (
                    ItemInstanceId(int(item_raw))
                    if item_raw is not None
                    else None
                )
            reserved = set(
                ItemInstanceId(int(i))
                for i in entry.get("reserved_item_ids", [])
            )
            # restore_from_data は AggregateRoot の super().__init__ を呼ぶので
            # 内部 _events は空で始まる。
            new_inv = PlayerInventoryAggregate.restore_from_data(
                player_id=pid,
                max_slots=max_slots,
                inventory_slots=inv_slots,
                equipment_slots=eq_slots,
                reserved_item_ids=reserved,
            )
            repo.save(new_inv)


__all__ = [
    "PlayerInventorySubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]
