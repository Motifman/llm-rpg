from typing import Optional
from abc import abstractmethod
from src.domain.common.repository import Repository
from src.domain.spot.area import Area


class AreaRepository(Repository[Area]):
    @abstractmethod
    def find_by_spot_id(self, spot_id: int) -> Optional[Area]:
        pass

    @abstractmethod
    def generate_area_id(self) -> int:
        """エリアIDを生成"""
        pass