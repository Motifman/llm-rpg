"""Phase 9-4b codec の単体テスト (weather / day_night)。"""

from __future__ import annotations

import random
from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    DayNightSubsystemCodec,
    WeatherSubsystemCodec,
)
from ai_rpg_world.application.world_graph.spot_graph_environment_stage_service import (
    SpotGraphEnvironmentStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
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

    def test_weather_holder_none_works(self) -> None:
        """scenario が天候を使わない構成: capture / restore が壊れない。"""
        runtime = SimpleNamespace(_current_weather=None)
        captured = WeatherSubsystemCodec().capture(runtime)
        assert captured["state"] is None
        WeatherSubsystemCodec().restore(runtime, captured)  # no-op

    def test_state_none_holder_works(self) -> None:
        """state が None の holder でも 動く。"""
        holder = {"state": None}
        runtime = SimpleNamespace(_current_weather=holder)
        captured = WeatherSubsystemCodec().capture(runtime)
        assert captured["state"] is None
        WeatherSubsystemCodec().restore(runtime, captured)
        assert holder["state"] is None

    def test_unsupported_schema_version_raises_exception_2(self) -> None:
        """未サポート schemaversion は例外。"""
        with pytest.raises(ValueError, match="schema_version"):
            WeatherSubsystemCodec().restore(
                SimpleNamespace(), {"schema_version": 999}
            )

    def test_round_trip_continues_weather_random_sequence(self) -> None:
        """snapshot再開後の次天候は連続実行と同じ乱数位置から決まる。"""
        src_holder = {
            "state": WeatherState(WeatherTypeEnum.CLEAR, 0.5),
        }
        src_stage = SpotGraphEnvironmentStageService(
            weather_state_provider=lambda: src_holder["state"],
            weather_state_setter=lambda state: src_holder.__setitem__("state", state),
            update_interval_ticks=1,
            random_source=random.Random(181),
        )
        src_runtime = SimpleNamespace(
            _current_weather=src_holder,
            _environment_stage=src_stage,
        )
        src_stage.run(WorldTick(1))
        captured = WeatherSubsystemCodec().capture(src_runtime)
        src_stage.run(WorldTick(2))
        expected = src_holder["state"]

        dst_holder = {
            "state": WeatherState(WeatherTypeEnum.STORM, 1.0),
        }
        dst_stage = SpotGraphEnvironmentStageService(
            weather_state_provider=lambda: dst_holder["state"],
            weather_state_setter=lambda state: dst_holder.__setitem__("state", state),
            update_interval_ticks=1,
            random_source=random.Random(999),
        )
        dst_runtime = SimpleNamespace(
            _current_weather=dst_holder,
            _environment_stage=dst_stage,
        )

        WeatherSubsystemCodec().restore(dst_runtime, captured)
        dst_stage.run(WorldTick(2))

        assert dst_holder["state"] == expected

    def test_v1_restore_keeps_runtime_random_position(self) -> None:
        """旧schema v1は天候だけを復元し、現在の専用乱数位置を変えない。"""
        holder = {
            "state": WeatherState(WeatherTypeEnum.CLEAR, 0.5),
        }
        stage = SpotGraphEnvironmentStageService(
            weather_state_provider=lambda: holder["state"],
            weather_state_setter=lambda state: holder.__setitem__("state", state),
            random_source=random.Random(181),
        )
        runtime = SimpleNamespace(
            _current_weather=holder,
            _environment_stage=stage,
        )
        original_random_state = stage.random_state()

        WeatherSubsystemCodec().restore(
            runtime,
            {
                "schema_version": 1,
                "state": {"weather_type": "RAIN", "intensity": 0.8},
            },
        )

        assert holder["state"] == WeatherState(WeatherTypeEnum.RAIN, 0.8)
        assert stage.random_state() == original_random_state

    def test_invalid_random_state_does_not_change_weather_or_rng(self) -> None:
        """壊れた乱数payloadは現天候と乱数位置を半端に変更せず拒否する。"""
        original = WeatherState(WeatherTypeEnum.CLEAR, 0.5)
        holder = {"state": original}
        stage = SpotGraphEnvironmentStageService(
            weather_state_provider=lambda: holder["state"],
            weather_state_setter=lambda state: holder.__setitem__("state", state),
            random_source=random.Random(181),
        )
        runtime = SimpleNamespace(
            _current_weather=holder,
            _environment_stage=stage,
        )
        original_random_state = stage.random_state()

        with pytest.raises(ValueError, match="random_state"):
            WeatherSubsystemCodec().restore(
                runtime,
                {
                    "schema_version": 2,
                    "state": {"weather_type": "RAIN", "intensity": 0.8},
                    "random_state": {
                        "state_version": 3,
                        "internal_state": [True],
                        "gaussian_cache": None,
                    },
                },
            )

        assert holder["state"] == original
        assert stage.random_state() == original_random_state

    @pytest.mark.parametrize(
        "random_state",
        [None, pytest.param("missing", id="missing")],
    )
    def test_v2_requires_random_state_when_weather_stage_exists(
        self,
        random_state: object,
    ) -> None:
        """schema v2は乱数位置の欠落を拒否し、天候と現在の乱数位置を保つ。"""
        original = WeatherState(WeatherTypeEnum.CLEAR, 0.5)
        holder = {"state": original}
        stage = SpotGraphEnvironmentStageService(
            weather_state_provider=lambda: holder["state"],
            weather_state_setter=lambda state: holder.__setitem__("state", state),
            random_source=random.Random(181),
        )
        runtime = SimpleNamespace(
            _current_weather=holder,
            _environment_stage=stage,
        )
        original_random_state = stage.random_state()
        payload = {
            "schema_version": 2,
            "state": {"weather_type": "RAIN", "intensity": 0.8},
        }
        if random_state != "missing":
            payload["random_state"] = random_state

        with pytest.raises(ValueError, match="random_state"):
            WeatherSubsystemCodec().restore(runtime, payload)

        assert holder["state"] == original
        assert stage.random_state() == original_random_state


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

    def test_includes_capture_phase_name(self) -> None:
        """capture は phasename を含む。"""
        stage = SimpleNamespace(
            _cycle=_StubCycle({0: _StubTimeOfDay("MORNING")}),
            _current=_StubTimeOfDay("MIDDAY"),
        )
        runtime = SimpleNamespace(_day_night_stage=stage)
        captured = DayNightSubsystemCodec().capture(runtime)
        assert captured["phase_name"] == "MIDDAY"

    def test_restore_tick(self) -> None:
        """restore は tick から再計算する。"""
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

    def test_day_night_stage_none_op(self) -> None:
        """day night stage が None なら no op。"""
        runtime = SimpleNamespace(_day_night_stage=None)
        captured = DayNightSubsystemCodec().capture(runtime)
        assert captured["phase_name"] is None
        DayNightSubsystemCodec().restore(
            runtime, {"schema_version": 1, "phase_name": None}
        )  # no error

    def test_unsupported_schema_version_raises_exception(self) -> None:
        """未サポート schemaversion は例外。"""
        with pytest.raises(ValueError, match="schema_version"):
            DayNightSubsystemCodec().restore(
                SimpleNamespace(), {"schema_version": 999}
            )
