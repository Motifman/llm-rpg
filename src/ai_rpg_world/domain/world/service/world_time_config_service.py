from abc import ABC, abstractmethod


class WorldTimeConfigService(ABC):
    """世界時間（昼夜サイクル・暦）に関する設定値を提供するドメインサービス"""

    @abstractmethod
    def get_ticks_per_day(self) -> int:
        """1日を表すティック数を取得"""
        pass

    @abstractmethod
    def get_days_per_month(self) -> int:
        """1か月を表す日数を取得"""
        pass

    @abstractmethod
    def get_months_per_year(self) -> int:
        """1年を表す月数を取得"""
        pass


class DefaultWorldTimeConfigService(WorldTimeConfigService):
    """デフォルトの世界時間設定実装"""

    def __init__(
        self,
        ticks_per_day: int = 86400,
        days_per_month: int = 30,
        months_per_year: int = 12,
    ) -> None:
        if ticks_per_day < 1:
            raise ValueError(f"ticks_per_day must be positive: {ticks_per_day}")
        if days_per_month < 1:
            raise ValueError(f"days_per_month must be positive: {days_per_month}")
        if months_per_year < 1:
            raise ValueError(f"months_per_year must be positive: {months_per_year}")
        self._ticks_per_day = ticks_per_day
        self._days_per_month = days_per_month
        self._months_per_year = months_per_year

    def get_ticks_per_day(self) -> int:
        return self._ticks_per_day

    def get_days_per_month(self) -> int:
        return self._days_per_month

    def get_months_per_year(self) -> int:
        return self._months_per_year
