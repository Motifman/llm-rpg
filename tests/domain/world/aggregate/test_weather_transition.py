import pytest
from ai_rpg_world.domain.world.aggregate.weather_zone import WeatherZone, InvalidWeatherTransitionException
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService


class TestWeatherTransition:
    """天候遷移ロジックのテスト"""

    def test_transition_constraints(self):
        """天候遷移の制約が正しく機能することを確認"""
        zone_id = WeatherZoneId("z1")
        # 晴れから開始
        zone = WeatherZone(zone_id, "Test", {SpotId(1)}, WeatherState.clear())

        # 晴れ -> 曇り は許可されている
        cloudy = WeatherState(WeatherTypeEnum.CLOUDY, 1.0)
        zone.change_weather(cloudy)
        assert zone.current_state.weather_type == WeatherTypeEnum.CLOUDY

        # 曇り -> 雨 は許可されている
        rain = WeatherState(WeatherTypeEnum.RAIN, 1.0)
        zone.change_weather(rain)
        assert zone.current_state.weather_type == WeatherTypeEnum.RAIN

        # 雨 -> 晴れ は許可されていない（雨の次は曇りか豪雨か嵐のみ）
        clear = WeatherState.clear()
        with pytest.raises(InvalidWeatherTransitionException):
            zone.change_weather(clear)

    def test_force_change_weather(self):
        """強制的な天候変更が制約を無視できることを確認"""
        zone = WeatherZone(WeatherZoneId("z1"), "Test", {SpotId(1)}, WeatherState(WeatherTypeEnum.RAIN, 1.0))
        
        # 強制的に晴れにする
        clear = WeatherState.clear()
        zone.change_weather(clear, force=True)
        assert zone.current_state.weather_type == WeatherTypeEnum.CLEAR

    def test_simulation_service_output(self):
        """シミュレーションサービスが制約に従った天候を返すことを確認"""
        zone = WeatherZone(WeatherZoneId("z1"), "Test", {SpotId(1)}, WeatherState.clear())
        
        for _ in range(10):
            next_state = WeatherSimulationService.simulate_next_weather(zone.current_state)
            # 晴れから遷移可能な天候であることを確認
            assert WeatherSimulationService.is_transition_allowed(zone.current_state.weather_type, next_state.weather_type)
            zone.change_weather(next_state)
