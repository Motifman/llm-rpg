from abc import abstractmethod
from typing import Optional, List
from src.domain.common.repository import Repository
from src.domain.spot.road import Road


class RoadRepository(Repository[Road]):
    """道路リポジトリインターフェース"""

    @abstractmethod
    def find_by_from_spot_id(self, from_spot_id: int) -> List[Road]:
        """出発地点から道路を検索"""
        pass
    
    @abstractmethod
    def find_between_spots(self, from_spot_id: int, to_spot_id: int) -> Optional[Road]:
        """2つのスポット間の道路を検索"""
        pass
    
    @abstractmethod
    def find_connected_to_spot(self, spot_id: int) -> List[Road]:
        """指定スポットに接続されている全ての道路を検索"""
        pass