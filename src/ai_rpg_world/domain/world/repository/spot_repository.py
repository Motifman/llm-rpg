from abc import ABC, abstractmethod
from typing import Optional, List, TYPE_CHECKING
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.entity.spot import Spot


class SpotRepository(Repository["Spot", SpotId], ABC):
    """スポットのリポジトリインターフェース（WorldMap に依存しない取得手段）"""

    @abstractmethod
    def find_by_id(self, spot_id: SpotId) -> Optional["Spot"]:
        """スポットIDでスポットを検索"""
        pass

    @abstractmethod
    def find_by_ids(self, spot_ids: List[SpotId]) -> List["Spot"]:
        """スポットIDのリストでスポットを検索"""
        pass

    @abstractmethod
    def save(self, spot: "Spot") -> "Spot":
        """スポットを保存"""
        pass

    @abstractmethod
    def delete(self, spot_id: SpotId) -> bool:
        """スポットを削除"""
        pass

    @abstractmethod
    def find_all(self) -> List["Spot"]:
        """全てのスポットを取得"""
        pass
