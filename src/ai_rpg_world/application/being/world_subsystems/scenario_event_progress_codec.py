"""Scenario event progress subsystem codec (Phase 9-3)。

``runtime._scenario_event_progress``
(``InMemorySpotGraphScenarioEventProgressStore``) は scenario_events の
発火状態を持つ:
- ``_fired_event_ids``: set[str] (= 既に発火済の event_id)
- ``_scheduled``: dict[str, int] (= 将来発火予定の event_id → fire_at_tick)

resume で **event が 2 回発火する** のを防ぐため必須。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "scenario_event_progress"
SCHEMA_VERSION = 1


class ScenarioEventProgressSubsystemCodec(WorldSubsystemCodec):
    """発火済 + scheduled な scenario_event を JSON 化。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        store = getattr(runtime, "_scenario_event_progress", None)
        if store is None:
            raise RuntimeError(
                "runtime._scenario_event_progress not found; "
                "ScenarioEventProgressSubsystemCodec requires it"
            )
        # fired は set, scheduled は dict。ソートで決定的に。
        fired = sorted(str(eid) for eid in store._fired_event_ids)
        scheduled = sorted(
            (
                {"event_id": str(eid), "fire_at_tick": int(tick)}
                for eid, tick in store._scheduled.items()
            ),
            key=lambda d: d["event_id"],
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "fired_event_ids": fired,
            "scheduled": scheduled,
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        store = getattr(runtime, "_scenario_event_progress", None)
        if store is None:
            raise RuntimeError(
                "runtime._scenario_event_progress not found; "
                "ScenarioEventProgressSubsystemCodec requires it"
            )
        # 内部 dict / set を直接書き換え (= clear + repopulate)。
        # public 経路 ``mark_fired`` / ``schedule`` でも復元可能だが、
        # 既存の値を消す手段がないので set / dict を直接置き換える方が安全。
        store._fired_event_ids.clear()
        for eid in data.get("fired_event_ids", []):
            store._fired_event_ids.add(str(eid))
        store._scheduled.clear()
        for entry in data.get("scheduled", []):
            store._scheduled[str(entry["event_id"])] = int(entry["fire_at_tick"])


__all__ = [
    "ScenarioEventProgressSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]
