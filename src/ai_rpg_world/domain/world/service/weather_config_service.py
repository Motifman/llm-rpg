from abc import ABC, abstractmethod


class WeatherConfigService(ABC):
    """天候シミュレーションに関する設定値を提供するドメインサービス"""

    @abstractmethod
    def get_update_interval_ticks(self) -> int:
        """天候を更新するティック間隔を取得"""
        pass


class DefaultWeatherConfigService(WeatherConfigService):
    """デフォルトの天候設定実装"""

    def __init__(self, update_interval_ticks: int = 100):
        self._update_interval_ticks = update_interval_ticks

    def get_update_interval_ticks(self) -> int:
        return self._update_interval_ticks
