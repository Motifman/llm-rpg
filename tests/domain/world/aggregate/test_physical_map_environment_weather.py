import pytest
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import EnvironmentTypeEnum


class TestPhysicalMapEnvironmentWeather:
    """PhysicalMapAggregateの環境による天候制限のテスト"""

    def test_outdoor_map_accepts_any_weather(self):
        """屋外マップは任意の天候を受け入れる"""
        map_agg = PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles={},
            environment_type=EnvironmentTypeEnum.OUTDOOR
        )
        
        storm = WeatherState(WeatherTypeEnum.STORM, 1.0)
        map_agg.set_weather(storm)
        
        assert map_agg._weather_state == storm

    def test_indoor_map_forces_clear_weather(self):
        """屋内マップは天候を常にCLEARにする"""
        map_agg = PhysicalMapAggregate(
            spot_id=SpotId(2),
            tiles={},
            environment_type=EnvironmentTypeEnum.INDOOR
        )
        
        storm = WeatherState(WeatherTypeEnum.STORM, 1.0)
        map_agg.set_weather(storm)
        
        # STORMをセットしようとしてもCLEARになる
        assert map_agg._weather_state.weather_type == WeatherTypeEnum.CLEAR
        assert map_agg._weather_state.intensity == 1.0

    def test_underground_map_forces_clear_weather(self):
        """地下マップは天候を常にCLEARにする"""
        map_agg = PhysicalMapAggregate(
            spot_id=SpotId(3),
            tiles={},
            environment_type=EnvironmentTypeEnum.UNDERGROUND
        )
        
        blizzard = WeatherState(WeatherTypeEnum.BLIZZARD, 0.8)
        map_agg.set_weather(blizzard)
        
        assert map_agg._weather_state.weather_type == WeatherTypeEnum.CLEAR
