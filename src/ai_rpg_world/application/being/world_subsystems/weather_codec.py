"""Weather state subsystem codec (Phase 9-4b)。

``runtime._current_weather`` は ``weather_holder`` (= dict) で、
``weather_holder["state"]`` に現天候の ``WeatherState`` を持つ。
``WeatherState`` は ``(weather_type: WeatherTypeEnum, intensity: float)``
の 2 フィールド。
"""

from __future__ import annotations

import random
from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "weather"
SCHEMA_VERSION = 2


class WeatherSubsystemCodec(WorldSubsystemCodec):
    """現天候 (weather_holder["state"]) を JSON 化。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        holder = getattr(runtime, "_current_weather", None)
        if holder is None:
            # scenario が天候を使わない: 空 capture
            return {
                "schema_version": SCHEMA_VERSION,
                "state": None,
                "random_state": self._capture_random_state(runtime),
            }
        weather_state = holder.get("state") if isinstance(holder, dict) else None
        if weather_state is None:
            return {
                "schema_version": SCHEMA_VERSION,
                "state": None,
                "random_state": self._capture_random_state(runtime),
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "state": {
                "weather_type": weather_state.weather_type.value,
                "intensity": float(weather_state.intensity),
            },
            "random_state": self._capture_random_state(runtime),
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version not in (1, SCHEMA_VERSION):
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected 1 or {SCHEMA_VERSION})"
            )
        restored_random_state = None
        if version == SCHEMA_VERSION:
            stage = getattr(runtime, "_environment_stage", None)
            supports_random_restore = stage is not None and hasattr(
                stage, "restore_random_state"
            )
            raw_random_state = data.get("random_state")
            if supports_random_restore and raw_random_state is None:
                raise ValueError(
                    f"{SUBSYSTEM_KEY}.random_state is required for schema v2"
                )
            restored_random_state = self._decode_random_state(raw_random_state)
        if restored_random_state is not None:
            stage = getattr(runtime, "_environment_stage", None)
            if stage is None or not hasattr(stage, "restore_random_state"):
                raise RuntimeError(
                    "runtime._environment_stage does not support weather random restore"
                )
        holder = getattr(runtime, "_current_weather", None)
        if holder is None or not isinstance(holder, dict):
            # scenario 側で weather を使わない構成: skip
            self._restore_random_state(runtime, restored_random_state)
            return
        state_data = data.get("state")
        if state_data is None:
            holder["state"] = None
            self._restore_random_state(runtime, restored_random_state)
            return
        from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
        from ai_rpg_world.domain.world.value_object.weather_state import (
            WeatherState,
        )

        holder["state"] = WeatherState(
            weather_type=WeatherTypeEnum(str(state_data["weather_type"])),
            intensity=float(state_data["intensity"]),
        )
        self._restore_random_state(runtime, restored_random_state)

    @staticmethod
    def _capture_random_state(runtime: Any) -> dict[str, Any] | None:
        stage = getattr(runtime, "_environment_stage", None)
        if stage is None or not hasattr(stage, "random_state"):
            return None
        state_version, internal_state, gaussian_cache = stage.random_state()
        return {
            "state_version": state_version,
            "internal_state": list(internal_state),
            "gaussian_cache": gaussian_cache,
        }

    @staticmethod
    def _decode_random_state(data: Any) -> object | None:
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError(f"{SUBSYSTEM_KEY}.random_state must be object or null")
        state_version = data.get("state_version")
        internal_state = data.get("internal_state")
        gaussian_cache = data.get("gaussian_cache")
        if isinstance(state_version, bool) or not isinstance(state_version, int):
            raise ValueError(f"{SUBSYSTEM_KEY}.random_state.state_version must be int")
        if not isinstance(internal_state, list) or not internal_state:
            raise ValueError(
                f"{SUBSYSTEM_KEY}.random_state.internal_state must be non-empty list"
            )
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in internal_state
        ):
            raise ValueError(
                f"{SUBSYSTEM_KEY}.random_state.internal_state must contain only int"
            )
        if gaussian_cache is not None and (
            isinstance(gaussian_cache, bool)
            or not isinstance(gaussian_cache, (int, float))
        ):
            raise ValueError(
                f"{SUBSYSTEM_KEY}.random_state.gaussian_cache must be number or null"
            )
        restored_state = (state_version, tuple(internal_state), gaussian_cache)
        validator = random.Random()
        try:
            validator.setstate(restored_state)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(
                f"{SUBSYSTEM_KEY}.random_state is invalid: {exc}"
            ) from exc
        return validator.getstate()

    @staticmethod
    def _restore_random_state(runtime: Any, state: object | None) -> None:
        if state is None:
            return
        stage = getattr(runtime, "_environment_stage", None)
        if stage is None or not hasattr(stage, "restore_random_state"):
            raise RuntimeError(
                "runtime._environment_stage does not support weather random restore"
            )
        stage.restore_random_state(state)


__all__ = ["WeatherSubsystemCodec", "SUBSYSTEM_KEY", "SCHEMA_VERSION"]
