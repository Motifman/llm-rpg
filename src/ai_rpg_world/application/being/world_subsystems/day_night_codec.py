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
        stage = getattr(runtime, "_day_night_stage", None)
        if stage is None:
            return {"schema_version": SCHEMA_VERSION, "phase_name": None}
        current = getattr(stage, "_current", None)
        return {
            "schema_version": SCHEMA_VERSION,
            "phase_name": current.phase_name if current is not None else None,
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        stage = getattr(runtime, "_day_night_stage", None)
        if stage is None:
            return
        time_provider = getattr(runtime, "_time_provider", None)
        if time_provider is None:
            # tick provider なしでは再計算できない (= 異常構成)
            return
        # tick から再導出 (= WorldTickSubsystemCodec が先に走っている前提)
        current_tick = time_provider.get_current_tick()
        cycle = getattr(stage, "_cycle", None)
        if cycle is None:
            return
        stage._current = cycle.time_of_day_at(current_tick)


__all__ = ["DayNightSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
