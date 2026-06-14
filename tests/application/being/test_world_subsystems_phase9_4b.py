"""Phase 9-4b codec の単体テスト (weather / day_night)。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    DayNightSubsystemCodec,
    WeatherSubsystemCodec,
)
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState


class TestWeatherCodec:
    """weather_holder["state"] の往復。"""

    def test_capture_restore_round_trip(self) -> None:
        src_holder = {
            "state": WeatherState(weather_type=WeatherTypeEnum.RAIN, intensity=0.8)
        }
        src_runtime = SimpleNamespace(_current_weather=src_holder)
        captured = WeatherSubsystemCodec().capture(src_runtime)
        assert captured["state"]["weather_type"] == "RAIN"
        assert captured["state"]["intensity"] == 0.8

        dst_holder = {
            "state": WeatherState(weather_type=WeatherTypeEnum.CLEAR, intensity=1.0)
        }
        dst_runtime = SimpleNamespace(_current_weather=dst_holder)
        WeatherSubsystemCodec().restore(dst_runtime, captured)
        assert dst_holder["state"].weather_type == WeatherTypeEnum.RAIN
        assert dst_holder["state"].intensity == 0.8

    def test_weather_holder_が_None_でも_動く(self) -> None:
        """scenario が天候を使わない構成: capture / restore が壊れない。"""
        runtime = SimpleNamespace(_current_weather=None)
        captured = WeatherSubsystemCodec().capture(runtime)
        assert captured["state"] is None
        WeatherSubsystemCodec().restore(runtime, captured)  # no-op

    def test_state_が_None_の_holder_でも_動く(self) -> None:
        holder = {"state": None}
        runtime = SimpleNamespace(_current_weather=holder)
        captured = WeatherSubsystemCodec().capture(runtime)
        assert captured["state"] is None
        WeatherSubsystemCodec().restore(runtime, captured)
        assert holder["state"] is None

    def test_未サポート_schema_version_は_例外(self) -> None:
        with pytest.raises(ValueError, match="schema_version"):
            WeatherSubsystemCodec().restore(
                SimpleNamespace(), {"schema_version": 999}
            )


class _StubCycle:
    """time_of_day_at(tick) を持つ最小 stub。"""

    def __init__(self, by_tick: dict[int, Any]) -> None:
        self._by_tick = by_tick
        self.lookup_calls: list[int] = []

    def time_of_day_at(self, tick: Any) -> Any:
        self.lookup_calls.append(int(tick.value))
        return self._by_tick.get(int(tick.value))


class _StubTimeOfDay:
    def __init__(self, phase_name: str) -> None:
        self.phase_name = phase_name


class _StubTimeProvider:
    """get_current_tick を持つ最小 stub。"""

    def __init__(self, tick_value: int) -> None:
        from ai_rpg_world.domain.common.value_object import WorldTick

        self._tick = WorldTick(tick_value)

    def get_current_tick(self):
        return self._tick


class TestDayNightCodec:
    """day_night._current を tick から再計算で復元。"""

    def test_capture_は_phase_name_を_含む(self) -> None:
        stage = SimpleNamespace(
            _cycle=_StubCycle({0: _StubTimeOfDay("MORNING")}),
            _current=_StubTimeOfDay("MIDDAY"),
        )
        runtime = SimpleNamespace(_day_night_stage=stage)
        captured = DayNightSubsystemCodec().capture(runtime)
        assert captured["phase_name"] == "MIDDAY"

    def test_restore_は_tick_から_再計算する(self) -> None:
        # cycle: tick=30 → "NIGHT"
        cycle = _StubCycle({30: _StubTimeOfDay("NIGHT")})
        stage = SimpleNamespace(
            _cycle=cycle,
            _current=_StubTimeOfDay("MORNING"),  # 復元前は別の phase
        )
        runtime = SimpleNamespace(
            _day_night_stage=stage,
            _time_provider=_StubTimeProvider(30),
        )
        # capture 結果は問わず restore できる (= 再計算なので)
        DayNightSubsystemCodec().restore(
            runtime, {"schema_version": 1, "phase_name": "ignored"}
        )
        assert stage._current.phase_name == "NIGHT"
        assert cycle.lookup_calls == [30]

    def test_day_night_stage_が_None_なら_no_op(self) -> None:
        runtime = SimpleNamespace(_day_night_stage=None)
        captured = DayNightSubsystemCodec().capture(runtime)
        assert captured["phase_name"] is None
        DayNightSubsystemCodec().restore(
            runtime, {"schema_version": 1, "phase_name": None}
        )  # no error

    def test_未サポート_schema_version_は_例外(self) -> None:
        with pytest.raises(ValueError, match="schema_version"):
            DayNightSubsystemCodec().restore(
                SimpleNamespace(), {"schema_version": 999}
            )
