"""未通知腐敗バッファ subsystem codec。

``WorldRuntime`` は腐敗通知を日次でまとめるため、当日分を
``_pending_spoiled`` / ``_pending_spoiled_day`` に一時保持する。ここを
snapshot しないと、日付境界前に resume したとき「今日は X が腐った」
という未通知観測だけが静かに欠ける。

この codec は flush のタイミングを変えず、未通知バッファだけを保存・復元する。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "pending_food_spoilage"
SCHEMA_VERSION = 1


class PendingFoodSpoilageSubsystemCodec(WorldSubsystemCodec):
    """未通知の腐敗集約バッファを JSON 化する。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        pending = getattr(runtime, "_pending_spoiled", None) or {}
        pending_day = getattr(runtime, "_pending_spoiled_day", None)
        entries = []
        for raw_spec_id, raw_entry in pending.items():
            entry = dict(raw_entry)
            spec_id = int(entry.get("spec_id", raw_spec_id))
            entries.append(
                {
                    "spec_id": spec_id,
                    "spec_name": entry.get("spec_name"),
                    # 同一 item spec 内は腐敗検出順を保つ。観測文の count は同じでも、
                    # trace 上の item_instance_ids は runtime が積んだ順序に揃える。
                    "instance_ids": [
                        int(instance_id)
                        for instance_id in entry.get("instance_ids", [])
                    ],
                }
            )
        entries.sort(key=lambda e: e["spec_id"])
        return {
            "schema_version": SCHEMA_VERSION,
            "pending_day": None if pending_day is None else int(pending_day),
            "entries": entries,
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        pending_day = data.get("pending_day")
        restored: dict[int, dict[str, Any]] = {}
        for raw_entry in data.get("entries", []):
            entry = dict(raw_entry)
            spec_id = int(entry["spec_id"])
            restored[spec_id] = {
                "spec_id": spec_id,
                "spec_name": entry.get("spec_name"),
                "instance_ids": [
                    int(instance_id) for instance_id in entry.get("instance_ids", [])
                ],
            }
        runtime._pending_spoiled = restored
        runtime._pending_spoiled_day = (
            None if pending_day is None else int(pending_day)
        )


__all__ = [
    "PendingFoodSpoilageSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]
