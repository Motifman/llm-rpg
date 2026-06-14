"""Weather state subsystem codec (Phase 9-4b)。

``runtime._current_weather`` は ``weather_holder`` (= dict) で、
``weather_holder["state"]`` に現天候の ``WeatherState`` を持つ。
``WeatherState`` は ``(weather_type: WeatherTypeEnum, intensity: float)``
の 2 フィールド。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "weather"
SCHEMA_VERSION = 1


class WeatherSubsystemCodec(WorldSubsystemCodec):
    """現天候 (weather_holder["state"]) を JSON 化。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        holder = getattr(runtime, "_current_weather", None)
        if holder is None:
            # scenario が天候を使わない: 空 capture
            return {"schema_version": SCHEMA_VERSION, "state": None}
        weather_state = holder.get("state") if isinstance(holder, dict) else None
        if weather_state is None:
            return {"schema_version": SCHEMA_VERSION, "state": None}
        return {
            "schema_version": SCHEMA_VERSION,
            "state": {
                "weather_type": weather_state.weather_type.value,
                "intensity": float(weather_state.intensity),
            },
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        holder = getattr(runtime, "_current_weather", None)
        if holder is None or not isinstance(holder, dict):
            # scenario 側で weather を使わない構成: skip
            return
        state_data = data.get("state")
        if state_data is None:
            holder["state"] = None
            return
        from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
        from ai_rpg_world.domain.world.value_object.weather_state import (
            WeatherState,
        )

        holder["state"] = WeatherState(
            weather_type=WeatherTypeEnum(str(state_data["weather_type"])),
            intensity=float(state_data["intensity"]),
        )


__all__ = ["WeatherSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
