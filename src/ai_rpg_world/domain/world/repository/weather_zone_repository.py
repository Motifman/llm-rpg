from abc import ABC, abstractmethod
from typing import List, Optional
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.world.aggregate.weather_zone import WeatherZone
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class WeatherZoneRepository(Repository[WeatherZone, WeatherZoneId]):
    """天候ゾーンの集約を永続化するためのリポジトリインターフェース"""

    @abstractmethod
    def save(self, weather_zone: WeatherZone) -> WeatherZone:
        """天候ゾーンを保存する"""
        pass

    @abstractmethod
    def find_by_id(self, zone_id: WeatherZoneId) -> Optional[WeatherZone]:
        """ゾーンIDで検索する"""
        pass

    @abstractmethod
    def find_by_ids(self, zone_ids: List[WeatherZoneId]) -> List[WeatherZone]:
        """複数のゾーンIDで検索する"""
        pass

    @abstractmethod
    def find_by_spot_id(self, spot_id: SpotId) -> Optional[WeatherZone]:
        """スポットIDが含まれる天候ゾーンを検索する"""
        pass

    @abstractmethod
    def find_all(self) -> List[WeatherZone]:
        """すべての天候ゾーンを取得する"""
        pass

    @abstractmethod
    def delete(self, zone_id: WeatherZoneId) -> bool:
        """天候ゾーンを削除する"""
        pass
