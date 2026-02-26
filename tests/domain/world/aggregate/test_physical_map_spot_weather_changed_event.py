"""SpotWeatherChangedEvent 発行のテスト（正常・境界・例外）"""

import pytest
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import EnvironmentTypeEnum
from ai_rpg_world.domain.world.event.map_events import SpotWeatherChangedEvent


class TestSpotWeatherChangedEventEmission:
    """屋外マップで天候が実際に変化した場合に SpotWeatherChangedEvent が発行されることを検証する"""

    @pytest.fixture
    def outdoor_aggregate(self):
        """屋外マップの集約（初期天候は CLEAR）"""
        return PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles={},
            environment_type=EnvironmentTypeEnum.OUTDOOR,
        )

    @pytest.fixture
    def indoor_aggregate(self):
        """屋内マップの集約"""
        return PhysicalMapAggregate(
            spot_id=SpotId(2),
            tiles={},
            environment_type=EnvironmentTypeEnum.INDOOR,
        )

    @pytest.fixture
    def underground_aggregate(self):
        """地下マップの集約"""
        return PhysicalMapAggregate(
            spot_id=SpotId(3),
            tiles={},
            environment_type=EnvironmentTypeEnum.UNDERGROUND,
        )

    class TestNormalOutdoorWeatherChange:
        """正常系: 屋外で天候が変化した場合にイベントが発行される"""

        def test_clear_to_rain_emits_event(self, outdoor_aggregate):
            """晴れから雨に変わったときにイベントが1件発行される"""
            outdoor_aggregate.clear_events()
            new_weather = WeatherState(WeatherTypeEnum.RAIN, 0.8)

            outdoor_aggregate.set_weather(new_weather)

            events = outdoor_aggregate.get_events()
            weather_events = [e for e in events if isinstance(e, SpotWeatherChangedEvent)]
            assert len(weather_events) == 1
            ev = weather_events[0]
            assert ev.spot_id == SpotId(1)
            assert ev.old_weather_state.weather_type == WeatherTypeEnum.CLEAR
            assert ev.old_weather_state.intensity == 1.0
            assert ev.new_weather_state.weather_type == WeatherTypeEnum.RAIN
            assert ev.new_weather_state.intensity == 0.8

        def test_rain_to_clear_emits_event(self, outdoor_aggregate):
            """雨から晴れに変わったときにイベントが1件発行される"""
            outdoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.RAIN, 1.0))
            outdoor_aggregate.clear_events()

            outdoor_aggregate.set_weather(WeatherState.clear())

            events = outdoor_aggregate.get_events()
            weather_events = [e for e in events if isinstance(e, SpotWeatherChangedEvent)]
            assert len(weather_events) == 1
            ev = weather_events[0]
            assert ev.old_weather_state.weather_type == WeatherTypeEnum.RAIN
            assert ev.new_weather_state.weather_type == WeatherTypeEnum.CLEAR

        def test_intensity_change_emits_event(self, outdoor_aggregate):
            """天候タイプが同じでも強度が変わればイベントが発行される"""
            outdoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.RAIN, 0.5))
            outdoor_aggregate.clear_events()

            outdoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.RAIN, 1.0))

            events = outdoor_aggregate.get_events()
            weather_events = [e for e in events if isinstance(e, SpotWeatherChangedEvent)]
            assert len(weather_events) == 1
            ev = weather_events[0]
            assert ev.old_weather_state.intensity == 0.5
            assert ev.new_weather_state.intensity == 1.0

        def test_storm_to_blizzard_emits_event(self, outdoor_aggregate):
            """嵐から吹雪に変わったときにイベントが発行される"""
            outdoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.STORM, 1.0))
            outdoor_aggregate.clear_events()

            outdoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.BLIZZARD, 0.9))

            events = outdoor_aggregate.get_events()
            weather_events = [e for e in events if isinstance(e, SpotWeatherChangedEvent)]
            assert len(weather_events) == 1
            ev = weather_events[0]
            assert ev.old_weather_state.weather_type == WeatherTypeEnum.STORM
            assert ev.new_weather_state.weather_type == WeatherTypeEnum.BLIZZARD

        def test_event_has_required_attributes(self, outdoor_aggregate):
            """発行されたイベントが aggregate_id, aggregate_type, event_id, occurred_at を持つ"""
            outdoor_aggregate.clear_events()
            outdoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.FOG, 1.0))

            events = outdoor_aggregate.get_events()
            weather_events = [e for e in events if isinstance(e, SpotWeatherChangedEvent)]
            assert len(weather_events) == 1
            ev = weather_events[0]
            assert ev.aggregate_id == SpotId(1)
            assert ev.aggregate_type == "PhysicalMap"
            assert ev.event_id is not None
            assert ev.occurred_at is not None

    class TestNoEventWhenUnchanged:
        """正常系: 天候が実質変化していない場合はイベントを発行しない"""

        def test_same_weather_set_again_emits_no_event(self, outdoor_aggregate):
            """同じ天候を再度設定してもイベントは発行されない"""
            outdoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.CLOUDY, 0.7))
            outdoor_aggregate.clear_events()

            outdoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.CLOUDY, 0.7))

            events = outdoor_aggregate.get_events()
            weather_events = [e for e in events if isinstance(e, SpotWeatherChangedEvent)]
            assert len(weather_events) == 0

        def test_initial_clear_to_clear_emits_no_event(self, outdoor_aggregate):
            """初期状態（CLEAR）のまま clear を設定してもイベントは発行されない"""
            outdoor_aggregate.clear_events()

            outdoor_aggregate.set_weather(WeatherState.clear())

            events = outdoor_aggregate.get_events()
            weather_events = [e for e in events if isinstance(e, SpotWeatherChangedEvent)]
            assert len(weather_events) == 0

    class TestIndoorAndUndergroundNoEvent:
        """境界系: 屋内・地下では天候変更イベントを発行しない"""

        def test_indoor_set_storm_emits_no_event(self, indoor_aggregate):
            """屋内で嵐を設定しても天候は CLEAR になり、イベントは発行されない"""
            indoor_aggregate.clear_events()

            indoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.STORM, 1.0))

            assert indoor_aggregate.weather_state.weather_type == WeatherTypeEnum.CLEAR
            events = indoor_aggregate.get_events()
            weather_events = [e for e in events if isinstance(e, SpotWeatherChangedEvent)]
            assert len(weather_events) == 0

        def test_underground_set_blizzard_emits_no_event(self, underground_aggregate):
            """地下で吹雪を設定しても天候は CLEAR になり、イベントは発行されない"""
            underground_aggregate.clear_events()

            underground_aggregate.set_weather(WeatherState(WeatherTypeEnum.BLIZZARD, 1.0))

            assert underground_aggregate.weather_state.weather_type == WeatherTypeEnum.CLEAR
            events = underground_aggregate.get_events()
            weather_events = [e for e in events if isinstance(e, SpotWeatherChangedEvent)]
            assert len(weather_events) == 0

    class TestMultipleChanges:
        """境界系: 連続して天候を変更した場合は変更ごとにイベントが発行される"""

        def test_two_consecutive_changes_emit_two_events(self, outdoor_aggregate):
            """晴れ→雨→嵐と連続で変更するとイベントが2件発行される"""
            outdoor_aggregate.clear_events()

            outdoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.RAIN, 1.0))
            outdoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.STORM, 1.0))

            events = outdoor_aggregate.get_events()
            weather_events = [e for e in events if isinstance(e, SpotWeatherChangedEvent)]
            assert len(weather_events) == 2
            assert weather_events[0].new_weather_state.weather_type == WeatherTypeEnum.RAIN
            assert weather_events[1].old_weather_state.weather_type == WeatherTypeEnum.RAIN
            assert weather_events[1].new_weather_state.weather_type == WeatherTypeEnum.STORM

    class TestEventPayloadConsistency:
        """イベントペイロードの一貫性"""

        def test_spot_id_matches_aggregate(self, outdoor_aggregate):
            """イベントの spot_id が集約の spot_id と一致する"""
            outdoor_aggregate.clear_events()
            outdoor_aggregate.set_weather(WeatherState(WeatherTypeEnum.SNOW, 0.5))

            events = outdoor_aggregate.get_events()
            ev = next(e for e in events if isinstance(e, SpotWeatherChangedEvent))
            assert ev.spot_id == outdoor_aggregate.spot_id

        def test_new_weather_state_matches_current_weather(self, outdoor_aggregate):
            """イベント発行後、集約の現在天候が new_weather_state と一致する"""
            new_weather = WeatherState(WeatherTypeEnum.HEAVY_RAIN, 0.6)
            outdoor_aggregate.clear_events()
            outdoor_aggregate.set_weather(new_weather)

            events = outdoor_aggregate.get_events()
            ev = next(e for e in events if isinstance(e, SpotWeatherChangedEvent))
            assert outdoor_aggregate.weather_state == ev.new_weather_state
            assert outdoor_aggregate.weather_state == new_weather
