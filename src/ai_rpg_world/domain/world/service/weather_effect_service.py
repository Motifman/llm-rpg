from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import EnvironmentTypeEnum


class WeatherEffectService:
    """天候による効果（視界低下、移動コスト増加）を計算するドメインサービス"""

    @staticmethod
    def calculate_stamina_multiplier(weather_state: WeatherState, env_type: EnvironmentTypeEnum) -> float:
        """天候によるスタミナ消費の倍率を計算する"""
        if env_type != EnvironmentTypeEnum.OUTDOOR:
            return 1.0

        multipliers = {
            WeatherTypeEnum.CLEAR: 1.0,
            WeatherTypeEnum.CLOUDY: 1.0,
            WeatherTypeEnum.RAIN: 1.1,
            WeatherTypeEnum.HEAVY_RAIN: 1.3,
            WeatherTypeEnum.SNOW: 1.2,
            WeatherTypeEnum.BLIZZARD: 1.8,
            WeatherTypeEnum.FOG: 1.0,
            WeatherTypeEnum.STORM: 1.5,
        }
        
        base_mult = multipliers.get(weather_state.weather_type, 1.0)
        if base_mult <= 1.0:
            return 1.0
            
        # 強度に応じて倍率を調整
        return 1.0 + (base_mult - 1.0) * weather_state.intensity

    @staticmethod
    def calculate_environmental_stamina_drain(weather_state: WeatherState, env_type: EnvironmentTypeEnum) -> int:
        """過酷な天候による継続的なスタミナ減少量（1ティックあたり）を計算する"""
        if env_type != EnvironmentTypeEnum.OUTDOOR:
            return 0

        drains = {
            WeatherTypeEnum.CLEAR: 0,
            WeatherTypeEnum.CLOUDY: 0,
            WeatherTypeEnum.RAIN: 0,
            WeatherTypeEnum.HEAVY_RAIN: 1,
            WeatherTypeEnum.SNOW: 0,
            WeatherTypeEnum.BLIZZARD: 3,
            WeatherTypeEnum.FOG: 0,
            WeatherTypeEnum.STORM: 2,
        }
        
        base_drain = drains.get(weather_state.weather_type, 0)
        if base_drain <= 0:
            return 0
            
        return int(base_drain * weather_state.intensity)

    @staticmethod
    def calculate_movement_cost_multiplier(weather_state: WeatherState, env_type: EnvironmentTypeEnum) -> float:
        """移動コストの倍率を計算する"""
        if env_type != EnvironmentTypeEnum.OUTDOOR:
            return 1.0

        multipliers = {
            WeatherTypeEnum.CLEAR: 1.0,
            WeatherTypeEnum.CLOUDY: 1.0,
            WeatherTypeEnum.RAIN: 1.2,
            WeatherTypeEnum.HEAVY_RAIN: 1.5,
            WeatherTypeEnum.SNOW: 1.3,
            WeatherTypeEnum.BLIZZARD: 2.0,
            WeatherTypeEnum.FOG: 1.1,
            WeatherTypeEnum.STORM: 1.8,
        }
        
        base_mult = multipliers.get(weather_state.weather_type, 1.0)
        if base_mult <= 1.0:
            return 1.0
            
        # 強度に応じて倍率を調整 (1.0 + (base - 1.0) * intensity)
        return 1.0 + (base_mult - 1.0) * weather_state.intensity

    @staticmethod
    def calculate_vision_reduction(weather_state: WeatherState, env_type: EnvironmentTypeEnum) -> int:
        """視界の減少距離（タイル数）を計算する"""
        if env_type != EnvironmentTypeEnum.OUTDOOR:
            return 0

        reductions = {
            WeatherTypeEnum.CLEAR: 0,
            WeatherTypeEnum.CLOUDY: 1,
            WeatherTypeEnum.RAIN: 2,
            WeatherTypeEnum.HEAVY_RAIN: 5,
            WeatherTypeEnum.SNOW: 2,
            WeatherTypeEnum.BLIZZARD: 10,
            WeatherTypeEnum.FOG: 8,
            WeatherTypeEnum.STORM: 6,
        }
        
        base_red = reductions.get(weather_state.weather_type, 0)
        return int(base_red * weather_state.intensity)

    @staticmethod
    def get_max_vision_distance(weather_state: WeatherState, env_type: EnvironmentTypeEnum) -> float:
        """天候による最大視認可能距離を返す（無限の場合は float('inf')）"""
        if env_type != EnvironmentTypeEnum.OUTDOOR:
            return float('inf')
            
        max_distances = {
            WeatherTypeEnum.CLEAR: float('inf'),
            WeatherTypeEnum.CLOUDY: 30.0,
            WeatherTypeEnum.RAIN: 15.0,
            WeatherTypeEnum.HEAVY_RAIN: 7.0,
            WeatherTypeEnum.SNOW: 12.0,
            WeatherTypeEnum.BLIZZARD: 3.0,
            WeatherTypeEnum.FOG: 5.0,
            WeatherTypeEnum.STORM: 8.0,
        }
        
        base_max = max_distances.get(weather_state.weather_type, float('inf'))
        if base_max == float('inf') or weather_state.intensity <= 0.0:
            return float('inf')
            
        return base_max / weather_state.intensity
