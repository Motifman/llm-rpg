from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    NoChange,
    WeatherDeclaration,
    WeatherState,
    WeatherType,
)
from ai_rpg_world.game_world.domain.value_object import WorldId
from ai_rpg_world.game_world.domain.world_progress import Weather, WeatherChangedEvent

_WORLD = WorldId("island")


def _declaration(initial: WeatherType) -> WeatherDeclaration:
    return WeatherDeclaration(initial=initial, changes=NoChange(), announce_changes=True, obscuring=frozenset())


class TestWeatherOpen:
    """Weather.open が、天候の宣言の initial から始まる天候を作ることを保証する。"""

    def test_starts_with_declared_initial_weather(self) -> None:
        """initial が霧の宣言から作った天候は、霧から始まる。"""
        weather = Weather.open(_WORLD, _declaration(WeatherType.FOG))

        assert weather.current() == WeatherState(WeatherType.FOG)
        assert weather.world_id == _WORLD

    def test_opening_records_no_event(self) -> None:
        """作っただけでは、イベントをためない。"""
        assert Weather.open(_WORLD, _declaration(WeatherType.FOG)).get_events() == []


class TestWeatherChange:
    """Weather.change が天候を書き換え、変わったときだけ前後の天候を持つイベントをためることを保証する。"""

    def test_change_replaces_current_weather(self) -> None:
        """晴れから雨へ change すると、current は雨になる。"""
        weather = Weather.open(_WORLD, _declaration(WeatherType.CLEAR))

        weather.change(WeatherState(WeatherType.RAIN))

        assert weather.current() == WeatherState(WeatherType.RAIN)

    def test_change_records_event_with_before_and_after(self) -> None:
        """晴れから雨への change は、世界と、変わる前の晴れと後の雨を持つ WeatherChangedEvent をためる。"""
        weather = Weather.open(_WORLD, _declaration(WeatherType.CLEAR))

        weather.change(WeatherState(WeatherType.RAIN))

        [event] = weather.get_events()
        assert isinstance(event, WeatherChangedEvent)
        assert (event.world_id, event.before, event.after) == (
            _WORLD,
            WeatherState(WeatherType.CLEAR),
            WeatherState(WeatherType.RAIN),
        )

    def test_change_to_same_weather_records_no_event(self) -> None:
        """今と同じ晴れへの change は、状態が変わらないので何もせず、イベントもためない。"""
        weather = Weather.open(_WORLD, _declaration(WeatherType.CLEAR))

        weather.change(WeatherState(WeatherType.CLEAR))

        assert weather.current() == WeatherState(WeatherType.CLEAR)
        assert weather.get_events() == []
