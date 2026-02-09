from typing import List, Optional, Dict, TYPE_CHECKING
from ai_rpg_world.domain.world.repository.world_map_repository import WorldMapRepository
from ai_rpg_world.domain.world.aggregate.world_map_aggregate import WorldMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.entity.spot import Spot


class InMemoryWorldMapRepository(WorldMapRepository, InMemoryRepositoryBase):
    """世界地図リポジトリのインメモリ実装"""
    
    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)
    
    @property
    def _world_maps(self) -> Dict[WorldId, WorldMapAggregate]:
        if not hasattr(self._data_store, 'world_maps'):
            self._data_store.world_maps = {}
        return self._data_store.world_maps

    @property
    def _spot_to_world_id(self) -> Dict[SpotId, WorldId]:
        if not hasattr(self._data_store, 'spot_to_world_id'):
            self._data_store.spot_to_world_id = {}
        return self._data_store.spot_to_world_id

    def find_by_id(self, world_id: WorldId) -> Optional[WorldMapAggregate]:
        """ワールドIDで世界地図を検索"""
        return self._world_maps.get(world_id)

    def find_by_ids(self, world_ids: List[WorldId]) -> List[WorldMapAggregate]:
        return [self._world_maps[wid] for wid in world_ids if wid in self._world_maps]
    
    def find_all_connected_spots(self, spot_id: SpotId) -> List[SpotId]:
        # 全ての世界地図から接続を検索
        connected = []
        for map_agg in self._world_maps.values():
            connected.extend(map_agg.get_connected_spots(spot_id))
        return list(set(connected))
    
    def save(self, world_map: WorldMapAggregate) -> WorldMapAggregate:
        def operation():
            """世界地図を保存"""
            self._world_maps[world_map.world_id] = world_map
            # スポットIDからワールドIDへのインデックスを更新
            for spot in world_map.get_all_spots():
                self._spot_to_world_id[spot.spot_id] = world_map.world_id
            return world_map
            
        return self._execute_operation(operation)
    
    def delete(self, world_id: WorldId) -> bool:
        def operation():
            if world_id in self._world_maps:
                world_map = self._world_maps[world_id]
                # インデックスから削除
                for spot in world_map.get_all_spots():
                    if self._spot_to_world_id.get(spot.spot_id) == world_id:
                        del self._spot_to_world_id[spot.spot_id]
                del self._world_maps[world_id]
                return True
            return False
            
        return self._execute_operation(operation)
    
    def find_spot_by_id(self, spot_id: SpotId) -> Optional["Spot"]:
        # インデックスを使用して高速に検索
        world_id = self._spot_to_world_id.get(spot_id)
        if world_id:
            world_map = self._world_maps.get(world_id)
            if world_map:
                try:
                    return world_map.get_spot(spot_id)
                except Exception:
                    # インデックスが古い、または集約内部で不整合
                    pass
        
        # インデックスにない、またはエラーが起きた場合は全検索（念のため）
        for map_agg in self._world_maps.values():
            try:
                return map_agg.get_spot(spot_id)
            except Exception:
                continue
        return None

    def find_by_spot_id(self, spot_id: SpotId) -> Optional[WorldMapAggregate]:
        """指定されたスポットを含む世界地図を取得"""
        world_id = self._spot_to_world_id.get(spot_id)
        if world_id:
            return self._world_maps.get(world_id)
            
        # インデックスにない場合は全検索
        for map_agg in self._world_maps.values():
            try:
                map_agg.get_spot(spot_id)
                return map_agg
            except Exception:
                continue
        return None

    def find_all(self) -> List[WorldMapAggregate]:
        return list(self._world_maps.values())
