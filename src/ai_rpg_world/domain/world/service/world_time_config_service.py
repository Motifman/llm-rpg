from abc import ABC, abstractmethod


class WorldTimeConfigService(ABC):
    """世界時間（昼夜サイクル）に関する設定値を提供するドメインサービス"""

    @abstractmethod
    def get_ticks_per_day(self) -> int:
        """1日を表すティック数を取得"""
        pass


class DefaultWorldTimeConfigService(WorldTimeConfigService):
    """デフォルトの世界時間設定実装"""

    def __init__(self, ticks_per_day: int = 96):
        if ticks_per_day < 1:
            raise ValueError(f"ticks_per_day must be positive: {ticks_per_day}")
        self._ticks_per_day = ticks_per_day

    def get_ticks_per_day(self) -> int:
        return self._ticks_per_day
