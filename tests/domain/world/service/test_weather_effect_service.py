import pytest
from ai_rpg_world.domain.world.service.weather_effect_service import WeatherEffectService
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import EnvironmentTypeEnum


class TestWeatherEffectService:
    """WeatherEffectServiceのテスト"""

    def test_calculate_movement_cost_multiplier_outdoor(self):
        # 晴れ
        state = WeatherState(WeatherTypeEnum.CLEAR, 1.0)
        mult = WeatherEffectService.calculate_movement_cost_multiplier(state, EnvironmentTypeEnum.OUTDOOR)
        assert mult == 1.0
        
        # 雨 (1.2倍)
        state = WeatherState(WeatherTypeEnum.RAIN, 1.0)
        mult = WeatherEffectService.calculate_movement_cost_multiplier(state, EnvironmentTypeEnum.OUTDOOR)
        assert mult == 1.2
        
        # 強度 0.5 の雨 -> 1.0 + (1.2 - 1.0) * 0.5 = 1.1
        state = WeatherState(WeatherTypeEnum.RAIN, 0.5)
        mult = WeatherEffectService.calculate_movement_cost_multiplier(state, EnvironmentTypeEnum.OUTDOOR)
        assert pytest.approx(mult) == 1.1

    def test_calculate_movement_cost_multiplier_indoor(self):
        # 嵐でも屋内なら影響なし
        state = WeatherState(WeatherTypeEnum.STORM, 1.0)
        mult = WeatherEffectService.calculate_movement_cost_multiplier(state, EnvironmentTypeEnum.INDOOR)
        assert mult == 1.0

    def test_calculate_vision_reduction(self):
        # 霧
        state = WeatherState(WeatherTypeEnum.FOG, 1.0)
        red = WeatherEffectService.calculate_vision_reduction(state, EnvironmentTypeEnum.OUTDOOR)
        assert red == 8
        
        # 強度 0.5 の霧
        state = WeatherState(WeatherTypeEnum.FOG, 0.5)
        red = WeatherEffectService.calculate_vision_reduction(state, EnvironmentTypeEnum.OUTDOOR)
        assert red == 4

    def test_get_max_vision_distance(self):
        # 吹雪
        state = WeatherState(WeatherTypeEnum.BLIZZARD, 1.0)
        max_dist = WeatherEffectService.get_max_vision_distance(state, EnvironmentTypeEnum.OUTDOOR)
        assert max_dist == 3.0
        
        # 強度 0.5 の吹雪 -> 3.0 / 0.5 = 6.0
        state = WeatherState(WeatherTypeEnum.BLIZZARD, 0.5)
        max_dist = WeatherEffectService.get_max_vision_distance(state, EnvironmentTypeEnum.OUTDOOR)
        assert max_dist == 6.0
        
        # 屋内
        max_dist = WeatherEffectService.get_max_vision_distance(state, EnvironmentTypeEnum.INDOOR)
        assert max_dist == float('inf')
