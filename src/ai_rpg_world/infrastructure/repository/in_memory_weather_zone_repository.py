from typing import List, Optional, Dict
from ai_rpg_world.domain.world.repository.weather_zone_repository import WeatherZoneRepository
from ai_rpg_world.domain.world.aggregate.weather_zone import WeatherZone
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemoryWeatherZoneRepository(WeatherZoneRepository, InMemoryRepositoryBase):
    """天候ゾーンリポジトリのインメモリ実装"""

    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)

    @property
    def _zones(self) -> Dict[WeatherZoneId, WeatherZone]:
        return self._data_store.weather_zones

    def save(self, weather_zone: WeatherZone) -> WeatherZone:
        cloned_zone = self._clone(weather_zone)
        def operation():
            self._zones[cloned_zone.zone_id] = cloned_zone
            return cloned_zone

        self._register_pending_if_uow(weather_zone.zone_id, weather_zone)
        return self._execute_operation(operation)

    def find_by_id(self, zone_id: WeatherZoneId) -> Optional[WeatherZone]:
        pending = self._get_pending_aggregate(zone_id)
        if pending is not None:
            return self._clone(pending)
        return self._clone(self._zones.get(zone_id))

    def find_by_ids(self, zone_ids: List[WeatherZoneId]) -> List[WeatherZone]:
        return [self._clone(self._zones[zid]) for zid in zone_ids if zid in self._zones]

    def find_by_spot_id(self, spot_id: SpotId) -> Optional[WeatherZone]:
        # 全てのゾーンを走査してスポットが含まれるものを探す
        target_sid_int = int(spot_id)
        for zone in self._zones.values():
            # spot_ids の中身を int で比較
            if any(int(sid) == target_sid_int for sid in zone.spot_ids):
                return self._clone(zone)
        return None

    def find_all(self) -> List[WeatherZone]:
        return [self._clone(zone) for zone in self._zones.values()]

    def delete(self, zone_id: WeatherZoneId) -> bool:
        def operation():
            if zone_id in self._zones:
                del self._zones[zone_id]
                return True
            return False
            
        return self._execute_operation(operation)
