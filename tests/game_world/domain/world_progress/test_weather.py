from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    NoChange,
    WeatherDeclaration,
    WeatherState,
    WeatherType,
)
from ai_rpg_world.game_world.domain.value_object import WorldId
from ai_rpg_world.game_world.domain.world_progress import Weather, WeatherChangedEvent
from tests.game_world.support.memento_for_tests import rebuilt_from_memento

_WORLD = WorldId("island")


def _declaration(initial: WeatherType) -> WeatherDeclaration:
    return WeatherDeclaration(initial=initial, changes=NoChange(), announce_changes=True, obscuring=frozenset())


class TestWeatherFromDeclaration:
    """Weather.from_declaration が、天候の宣言の initial から始まる天候を作ることを保証する。"""

    def test_starts_with_declared_initial_weather(self) -> None:
        """initial が霧の宣言から作った天候は、霧から始まる。"""
        weather = Weather.from_declaration(_WORLD, _declaration(WeatherType.FOG))

        assert weather.current() == WeatherState(WeatherType.FOG)
        assert weather.world_id == _WORLD

    def test_creating_records_no_event(self) -> None:
        """作っただけでは、イベントをためない。"""
        assert Weather.from_declaration(_WORLD, _declaration(WeatherType.FOG)).get_events() == []


class TestWeatherChange:
    """Weather.change が天候を書き換え、変わったときだけ前後の天候を持つイベントをためることを保証する。"""

    def test_change_replaces_current_weather(self) -> None:
        """晴れから雨へ change すると、current は雨になる。"""
        weather = Weather.from_declaration(_WORLD, _declaration(WeatherType.CLEAR))

        weather.change(WeatherState(WeatherType.RAIN))

        assert weather.current() == WeatherState(WeatherType.RAIN)

    def test_change_records_event_with_before_and_after(self) -> None:
        """晴れから雨への change は、世界と、変わる前の晴れと後の雨を持つ WeatherChangedEvent をためる。"""
        weather = Weather.from_declaration(_WORLD, _declaration(WeatherType.CLEAR))

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
        weather = Weather.from_declaration(_WORLD, _declaration(WeatherType.CLEAR))

        weather.change(WeatherState(WeatherType.CLEAR))

        assert weather.current() == WeatherState(WeatherType.CLEAR)
        assert weather.get_events() == []


class TestWeatherMemento:
    """Weather を memento から作り直すと、今の天候が元と同じになり、イベントは出ないことを保証する。"""

    def test_rebuilt_weather_is_the_same(self) -> None:
        """霧から雨に変わった天候を作り直すと、雨のまま。"""
        weather = Weather.from_declaration(_WORLD, _declaration(WeatherType.FOG))
        weather.change(WeatherState(WeatherType.RAIN))

        rebuilt = rebuilt_from_memento(weather)

        assert rebuilt.memento() == weather.memento()
        assert rebuilt.current() == WeatherState(WeatherType.RAIN)
        assert rebuilt.world_id == _WORLD

    def test_rebuilding_records_no_event(self) -> None:
        """変わったあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        weather = Weather.from_declaration(_WORLD, _declaration(WeatherType.FOG))
        weather.change(WeatherState(WeatherType.RAIN))

        assert rebuilt_from_memento(weather).get_events() == []
