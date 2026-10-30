"""Day/night cycle subsystem codec (Phase 9-4b)。

``runtime._day_night_stage`` は ``SpotGraphDayNightStageService``。内部の
``_current`` (= ``TimeOfDay``) は ``_cycle.time_of_day_at(world_tick)`` で
derivable なので、**restore で再計算** すれば足りる (= world_tick が
WorldTickSubsystemCodec で先に復元されている前提)。

capture では sanity 用に現 phase_name を保存し、restore 後と一致するか
任意で確認できる。

## 依存順序

本 codec は WorldTickSubsystemCodec の **後** に restore される必要がある
(= 再計算が tick に依存する)。``_default_world_subsystem_codecs()`` の
順序で保証している。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "day_night"
SCHEMA_VERSION = 1


class DayNightSubsystemCodec(WorldSubsystemCodec):
    """day/night cycle の ``_current`` を再計算 restore する。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        stage = runtime._day_night_stage
        if stage is None:
            return {"schema_version": SCHEMA_VERSION, "phase_name": None}
        return {
            "schema_version": SCHEMA_VERSION,
            "phase_name": stage._current.phase_name,
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported (expected {SCHEMA_VERSION})")
        stage = runtime._day_night_stage
        if stage is None:
            return
        # tick から再導出 (= WorldTickSubsystemCodec が先に走っている前提)
        current_tick = runtime._time_provider.get_current_tick()
        stage._current = stage._cycle.time_of_day_at(current_tick)


__all__ = ["DayNightSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
