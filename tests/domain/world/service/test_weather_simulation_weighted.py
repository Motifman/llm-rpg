import pytest
import random
from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum


class TestWeatherSimulationWeighted:
    """WeatherSimulationServiceの重み付き遷移テスト"""

    def test_weighted_simulation_distribution(self):
        """重み付きシミュレーションが統計的に正しい分布になるかテスト"""
        # CLEAR からの遷移を 1000 回試行
        current_state = WeatherState.clear()
        results = {}
        
        iterations = 1000
        for _ in range(iterations):
            next_state = WeatherSimulationService.simulate_next_weather(current_state)
            w_type = next_state.weather_type
            results[w_type] = results.get(w_type, 0) + 1
            
        # CLEAR: 70%, CLOUDY: 25%, FOG: 5% の重み設定
        # 統計的なマージンを持って確認
        assert 600 < results.get(WeatherTypeEnum.CLEAR, 0) < 800
        assert 150 < results.get(WeatherTypeEnum.CLOUDY, 0) < 350
        assert 10 < results.get(WeatherTypeEnum.FOG, 0) < 100
        
        # それ以外の天候は発生しないはず
        allowed = {WeatherTypeEnum.CLEAR, WeatherTypeEnum.CLOUDY, WeatherTypeEnum.FOG}
        for w_type in results.keys():
            assert w_type in allowed

    def test_all_weather_types_have_rules(self):
        """全ての天候タイプに対して遷移ルールが定義されているか"""
        for w_type in WeatherTypeEnum:
            assert w_type in WeatherSimulationService.TRANSITION_WEIGHTS
            weights = WeatherSimulationService.TRANSITION_WEIGHTS[w_type]
            assert len(weights) > 0
            assert all(isinstance(w, int) and w > 0 for w in weights.values())

    def test_is_transition_allowed(self):
        """遷移の許可判定テスト"""
        # CLEAR -> CLOUDY は許可されている
        assert WeatherSimulationService.is_transition_allowed(WeatherTypeEnum.CLEAR, WeatherTypeEnum.CLOUDY)
        # CLEAR -> STORM は許可されていない
        assert not WeatherSimulationService.is_transition_allowed(WeatherTypeEnum.CLEAR, WeatherTypeEnum.STORM)
        # BLIZZARD -> SNOW は許可されている
        assert WeatherSimulationService.is_transition_allowed(WeatherTypeEnum.BLIZZARD, WeatherTypeEnum.SNOW)
        # BLIZZARD -> CLEAR は許可されていない
        assert not WeatherSimulationService.is_transition_allowed(WeatherTypeEnum.BLIZZARD, WeatherTypeEnum.CLEAR)
