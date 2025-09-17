from typing import Optional
from src.domain.common.repository import Repository
from src.domain.spot.area import Area


class AreaRepository(Repository[Area]):
    def find_by_spot_id(self, spot_id: int) -> Optional[Area]:
        pass