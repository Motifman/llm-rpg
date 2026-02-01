from abc import ABC, abstractmethod
from typing import Optional, List
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class WorldMapRepository(Repository["WorldMapAggregate", SpotId], ABC):
    """意味マップ（世界地図）のリポジトリインターフェース"""
    
    @abstractmethod
    def find_all_connected_spots(self, spot_id: SpotId) -> List[SpotId]:
        """指定されたスポットに接続されている全てのスポットを取得"""
        pass
