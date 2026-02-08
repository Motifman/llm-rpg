import random
from typing import Dict, List, Set, Optional
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState


class WeatherSimulationService:
    """
    天候の遷移ロジックを管理するドメインサービス。
    妥当な遷移（例：晴れの次は曇りか雨）を保証し、重み付き確率でシミュレーションする。
    """

    # 天候の遷移規則と重み
    # {現在の天候: {次になり得る天候: 重み}}
    # 重みが大きいほど、その天候になりやすい。
    TRANSITION_WEIGHTS: Dict[WeatherTypeEnum, Dict[WeatherTypeEnum, int]] = {
        WeatherTypeEnum.CLEAR: {
            WeatherTypeEnum.CLEAR: 70, 
            WeatherTypeEnum.CLOUDY: 25, 
            WeatherTypeEnum.FOG: 5
        },
        WeatherTypeEnum.CLOUDY: {
            WeatherTypeEnum.CLEAR: 30, 
            WeatherTypeEnum.CLOUDY: 40, 
            WeatherTypeEnum.RAIN: 15, 
            WeatherTypeEnum.SNOW: 5, 
            WeatherTypeEnum.FOG: 10
        },
        WeatherTypeEnum.RAIN: {
            WeatherTypeEnum.CLOUDY: 30, 
            WeatherTypeEnum.RAIN: 40, 
            WeatherTypeEnum.HEAVY_RAIN: 20, 
            WeatherTypeEnum.STORM: 10
        },
        WeatherTypeEnum.HEAVY_RAIN: {
            WeatherTypeEnum.RAIN: 50, 
            WeatherTypeEnum.HEAVY_RAIN: 30, 
            WeatherTypeEnum.STORM: 20
        },
        WeatherTypeEnum.SNOW: {
            WeatherTypeEnum.CLOUDY: 40, 
            WeatherTypeEnum.SNOW: 50, 
            WeatherTypeEnum.BLIZZARD: 10
        },
        WeatherTypeEnum.BLIZZARD: {
            WeatherTypeEnum.SNOW: 60, 
            WeatherTypeEnum.BLIZZARD: 40
        },
        WeatherTypeEnum.FOG: {
            WeatherTypeEnum.CLEAR: 40, 
            WeatherTypeEnum.CLOUDY: 30, 
            WeatherTypeEnum.FOG: 30
        },
        WeatherTypeEnum.STORM: {
            WeatherTypeEnum.RAIN: 40, 
            WeatherTypeEnum.HEAVY_RAIN: 30, 
            WeatherTypeEnum.STORM: 30
        }
    }

    @classmethod
    def get_possible_transitions(cls, current_weather: WeatherTypeEnum) -> Set[WeatherTypeEnum]:
        """現在の天候から遷移可能な天候のリストを返す"""
        return set(cls.TRANSITION_WEIGHTS.get(current_weather, {WeatherTypeEnum.CLEAR: 1}).keys())

    @classmethod
    def simulate_next_weather(cls, current_state: WeatherState) -> WeatherState:
        """
        制約に従って次の天候を決定する（重み付きランダムシミュレーション）。
        """
        weights_dict = cls.TRANSITION_WEIGHTS.get(current_state.weather_type, {WeatherTypeEnum.CLEAR: 1})
        
        # 重み付き選択
        choices = list(weights_dict.keys())
        weights = list(weights_dict.values())
        
        next_type = random.choices(choices, weights=weights, k=1)[0]
        
        # 強度の変化（現在の強度から ±0.2 の範囲で変動させる、0.1〜1.0に収める）
        delta = (random.random() * 0.4) - 0.2
        next_intensity = max(0.1, min(1.0, current_state.intensity + delta))
        
        return WeatherState(next_type, next_intensity)

    @classmethod
    def is_transition_allowed(cls, from_type: WeatherTypeEnum, to_type: WeatherTypeEnum) -> bool:
        """天候の遷移が許可されているか判定する"""
        allowed_weights = cls.TRANSITION_WEIGHTS.get(from_type, {})
        return to_type in allowed_weights
