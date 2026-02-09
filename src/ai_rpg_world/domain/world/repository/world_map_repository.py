from abc import ABC, abstractmethod
from typing import Optional, List
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


class WorldMapRepository(Repository["WorldMapAggregate", WorldId], ABC):
    """意味マップ（世界地図）のリポジトリインターフェース"""
    
    @abstractmethod
    def find_all_connected_spots(self, spot_id: SpotId) -> List[SpotId]:
        """指定されたスポットに接続されている全てのスポットを取得"""
        pass

    @abstractmethod
    def find_spot_by_id(self, spot_id: SpotId) -> Optional["Spot"]:
        """指定されたスポットIDを持つスポットを全ての世界地図から検索"""
        pass

    @abstractmethod
    def find_by_spot_id(self, spot_id: SpotId) -> Optional["WorldMapAggregate"]:
        """指定されたスポットを含む世界地図を取得"""
        pass

    @abstractmethod
    def find_all(self) -> List["WorldMapAggregate"]:
        """全ての世界地図を取得"""
        pass
