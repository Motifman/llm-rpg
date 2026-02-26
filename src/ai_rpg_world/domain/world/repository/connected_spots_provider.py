from abc import ABC, abstractmethod
from typing import List
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class IConnectedSpotsProvider(ABC):
    """指定スポットから接続されているスポットID一覧を提供するポート（WorldMap に依存しない）"""

    @abstractmethod
    def get_connected_spots(self, spot_id: SpotId) -> List[SpotId]:
        """指定されたスポットに接続されているスポットIDのリストを返す"""
        pass
