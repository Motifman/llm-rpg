from abc import abstractmethod
from typing import Optional, List
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.spot.spot import Spot


class SpotRepository(Repository[Spot]):
    """スポットリポジトリインターフェース"""
    
    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Spot]:
        """名前でスポットを検索"""
        pass
    
    @abstractmethod
    def find_by_area_id(self, area_id: int) -> List[Spot]:
        """指定されたエリアのスポットを検索"""
        pass
    
    @abstractmethod
    def find_connected_spots(self, spot_id: int) -> List[Spot]:
        """指定されたスポットと接続されているスポットを検索"""
        pass

    @abstractmethod
    def generate_spot_id(self) -> int:
        """スポットIDを生成"""
        pass
