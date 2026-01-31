from typing import Optional
from abc import abstractmethod
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.spot.area import Area


class AreaRepository(Repository[Area]):
    @abstractmethod
    def find_by_spot_id(self, spot_id: int) -> Optional[Area]:
        pass

    @abstractmethod
    def generate_area_id(self) -> int:
        """エリアIDを生成"""
        pass