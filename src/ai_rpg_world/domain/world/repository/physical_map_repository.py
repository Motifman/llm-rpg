from abc import ABC, abstractmethod
from typing import Optional
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class PhysicalMapRepository(Repository["PhysicalMapAggregate", SpotId], ABC):
    """物理マップ（タイルマップ）のリポジトリインターフェース"""
    
    @abstractmethod
    def find_by_spot_id(self, spot_id: SpotId) -> Optional["PhysicalMapAggregate"]:
        """スポットIDで物理マップを検索（find_by_idと同じ役割だが明示的）"""
        pass
